#!/usr/bin/env python3
"""
サブグループメンバー選択ウィジェット共通クラス
新規作成タブの実装をベースに、修正タブでも使用可能な共通化実装
"""

import json
import os
import urllib.parse
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QCheckBox, QPushButton, QHBoxLayout, 
    QMessageBox, QDialog, QTextEdit, QTableWidget, QTableWidgetItem, 
    QHeaderView, QRadioButton, QButtonGroup, QLineEdit
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from config.common import SUBGROUP_JSON_PATH
from net.http_helpers import proxy_get


class CommonSubgroupMemberSelector(QWidget):
    """
    サブグループメンバー選択ウィジェット（共通実装）
    新規作成・修正タブ両方で使用可能
    """
    
    def __init__(self, user_entries=None, initial_roles=None, prechecked_user_ids=None, subgroup_id=None):
        """
        Args:
            user_entries: ユーザーリスト（Noneの場合は統合リストを自動読み込み）
            initial_roles: 初期ロール情報 (dict: user_id -> role)
            prechecked_user_ids: 初期選択ユーザーID (set)
            subgroup_id: 修正対象のサブグループID（新規作成時はNone）
        """
        super().__init__()
        self.subgroup_id = subgroup_id
        self.initial_roles = initial_roles or {}
        self.prechecked_user_ids = set(prechecked_user_ids or [])
        self.dynamic_users = []  # 動的に追加されたユーザーリスト
        self.user_rows = []
        self.owner_radio_group = QButtonGroup(self)
        self.owner_radio_group.setExclusive(True)
        
        # ユーザーエントリーを設定（統合リスト使用）
        if user_entries is None:
            self.load_unified_user_entries()
        else:
            self.user_entries = user_entries
        
        self.setup_ui()
    
    def load_unified_user_entries(self):
        """統合ユーザーエントリーを読み込み"""
        try:
            from ..core import subgroup_api_helper
            
            # 一時ファイルから動的ユーザーを読み込み
            temp_dynamic_users = subgroup_api_helper.load_dynamic_users_from_temp()
            
            # メモリ上の動的ユーザーと統合
            all_dynamic_users = list(self.dynamic_users)  # コピー
            
            # 一時ファイルのユーザーを追加（重複回避）
            existing_ids = {user.get('id', '') for user in all_dynamic_users}
            for temp_user in temp_dynamic_users:
                if temp_user.get('id', '') not in existing_ids:
                    all_dynamic_users.append(temp_user)
            
            unified_users, member_info = subgroup_api_helper.load_unified_member_list(
                subgroup_id=self.subgroup_id,
                dynamic_users=all_dynamic_users,
                bearer_token=getattr(self, 'bearer_token', None)
            )
            self.user_entries = unified_users
            self.member_info = member_info
            print(f"[DEBUG] 統合メンバーリスト読み込み完了: {len(unified_users)}名（一時ファイル含む）")
        except Exception as e:
            print(f"[ERROR] 統合メンバーリスト読み込みエラー: {e}")
            # フォールバック: 既存の方法を使用
            try:
                from .subgroup_ui_helpers import load_user_entries
                self.user_entries = load_user_entries()
                self.member_info = {}
            except Exception as fallback_error:
                print(f"[ERROR] フォールバック処理もエラー: {fallback_error}")
                self.user_entries = []
                self.member_info = {}
    
    def setup_ui(self):
        """UIセットアップ"""
        layout = QVBoxLayout()
        # 余白を最小限に設定
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # ユーザー動的追加UI
        add_user_layout = QHBoxLayout()
        add_user_layout.addWidget(QLabel("メールアドレス:"))
        
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("例: tanaka@example.com")
        add_user_layout.addWidget(self.email_input)
        
        self.add_user_button = QPushButton("ユーザー追加")
        self.add_user_button.clicked.connect(self.add_user_by_email)
        add_user_layout.addWidget(self.add_user_button)
        
        layout.addLayout(add_user_layout)
        
        if isinstance(self.user_entries, str):
            layout.addWidget(QLabel(self.user_entries))
        elif self.user_entries is None:
            layout.addWidget(QLabel("subGroup.jsonが見つかりません"))
        else:
            # カスタムテーブルウィジェット作成
            self.table = self.create_custom_table()
            self.populate_table()
            
            layout.addWidget(self.table)
        
        self.setLayout(layout)
    
    def create_custom_table(self):
        """カスタムテーブルウィジェット作成"""
        class CustomTableWidget(QTableWidget):
            def __init__(self, parent_selector):
                super().__init__()
                self.parent_selector = parent_selector
                self.column_sort_order = {}
                self.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
            
            def on_header_clicked(self, logical_index):
                """ヘッダークリック時の処理"""
                print(f"[DEBUG] ヘッダークリック: 列={logical_index}")

                if logical_index in [2, 3, 4, 5, 6]:  # OWNER/ASSISTANT/MEMBER/AGENT/VIEWER列
                    print(f"[DEBUG] チェックボックス/ラジオボタン列のソート実行")
                    
                    # 現在の列のソート状態を取得/切り替え
                    current_order = self.column_sort_order.get(logical_index, Qt.DescendingOrder)
                    new_order = Qt.AscendingOrder if current_order == Qt.DescendingOrder else Qt.DescendingOrder
                    
                    # ソート状態を記録
                    self.column_sort_order[logical_index] = new_order
                    
                    # ソートインジケーターを設定
                    self.horizontalHeader().setSortIndicator(logical_index, new_order)
                    
                    print(f"[DEBUG] ソート順序: {current_order} → {new_order}")
                    
                    # カスタムソート実行
                    self._sort_by_checkbox_state(logical_index, new_order)
                    return
                
                # 通常の列は標準ソート
                print(f"[DEBUG] 通常列のソート実行")
                current_order = self.column_sort_order.get(logical_index, Qt.DescendingOrder)
                new_order = Qt.AscendingOrder if current_order == Qt.DescendingOrder else Qt.DescendingOrder
                
                # ソート状態を記録
                self.column_sort_order[logical_index] = new_order
                
                # ソートインジケーターを設定
                self.horizontalHeader().setSortIndicator(logical_index, new_order)
                
                print(f"[DEBUG] 通常列ソート順序: {current_order} → {new_order}")
                
                # 標準のソート処理を実行
                super().sortByColumn(logical_index, new_order)
            
            def _sort_by_checkbox_state(self, column, order):
                """チェックボックス/ラジオボタン状態によるソート"""
                print(f"[DEBUG] チェックボックスソート開始: 列={column}, 順序={order}")
                
                if self.rowCount() == 0:
                    print("[DEBUG] 行が0件のためソートをスキップ")
                    return
                
                # 現在の行データを収集
                rows_data = []
                for i in range(self.rowCount()):
                    widget = self.cellWidget(i, column)
                    
                    # チェック状態を取得
                    if hasattr(widget, 'isChecked'):
                        checked = widget.isChecked()
                    else:
                        checked = False
                    
                    # 行データを収集
                    row_info = {
                        'original_index': i,
                        'checked': checked,
                        'member_name': self.item(i, 0).text() if self.item(i, 0) else "",
                        'email': self.item(i, 1).text() if self.item(i, 1) else "",
                        'owner_checked': self.cellWidget(i, 2).isChecked() if self.cellWidget(i, 2) else False,
                        'assistant_checked': self.cellWidget(i, 3).isChecked() if self.cellWidget(i, 3) else False,
                        'member_checked': self.cellWidget(i, 4).isChecked() if self.cellWidget(i, 4) else False,
                        'agent_checked': self.cellWidget(i, 5).isChecked() if self.cellWidget(i, 5) else False,
                        'viewer_checked': self.cellWidget(i, 6).isChecked() if self.cellWidget(i, 6) else False,
                        'owner_user_id': getattr(self.cellWidget(i, 2), 'user_id', '') if self.cellWidget(i, 2) else '',
                        'assistant_user_id': getattr(self.cellWidget(i, 3), 'user_id', '') if self.cellWidget(i, 3) else '',
                        'member_user_id': getattr(self.cellWidget(i, 4), 'user_id', '') if self.cellWidget(i, 4) else '',
                        'agent_user_id': getattr(self.cellWidget(i, 5), 'user_id', '') if self.cellWidget(i, 5) else '',
                        'viewer_user_id': getattr(self.cellWidget(i, 6), 'user_id', '') if self.cellWidget(i, 6) else ''
                    }
                    rows_data.append(row_info)
                    
                    print(f"[DEBUG] 行{i}: {row_info['member_name']}, チェック={checked}")
                
                # ソート実行
                reverse_sort = (order == Qt.DescendingOrder)
                rows_data.sort(key=lambda x: (not x['checked'], x['member_name']), reverse=reverse_sort)
                
                print(f"[DEBUG] ソート後順序: {len(rows_data)}行")
                
                # テーブルを再構築
                self._rebuild_table(rows_data)
            
            def _rebuild_table(self, sorted_rows_data):
                """ソート後のテーブル再構築"""
                print(f"[DEBUG] テーブル再構築開始: {len(sorted_rows_data)}行")
                
                # 必要なクラスをインポート
                from PyQt5.QtWidgets import QCheckBox, QRadioButton
                from PyQt5.QtCore import Qt
                from PyQt5.QtWidgets import QTableWidgetItem
                
                # ソートを一時無効化
                self.setSortingEnabled(False)
                
                # 行をクリア
                self.setRowCount(0)
                self.setRowCount(len(sorted_rows_data))
                
                # 新しい順序で行を再構築
                for new_row, row_data in enumerate(sorted_rows_data):
                    # テキストアイテム
                    name_item = QTableWidgetItem(row_data['member_name'])
                    name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self.setItem(new_row, 0, name_item)
                    
                    email_item = QTableWidgetItem(row_data['email'])
                    email_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self.setItem(new_row, 1, email_item)
                    
                    # OWNERラジオボタン再作成
                    owner_radio = QRadioButton()
                    owner_radio.user_id = row_data['owner_user_id']
                    owner_radio.setChecked(row_data['owner_checked'])
                    self.setCellWidget(new_row, 2, owner_radio)
                    
                    # ASSISTANTチェックボックス再作成
                    assistant_cb = QCheckBox()
                    assistant_cb.user_id = row_data['assistant_user_id']
                    assistant_cb.setChecked(row_data['assistant_checked'])
                    self.setCellWidget(new_row, 3, assistant_cb)
                    
                    # MEMBERチェックボックス再作成
                    member_cb = QCheckBox()
                    member_cb.user_id = row_data['member_user_id']
                    member_cb.setChecked(row_data['member_checked'])
                    self.setCellWidget(new_row, 4, member_cb)

                    # AGENTチェックボックス再作成
                    agent_cb = QCheckBox()
                    agent_cb.user_id = row_data['agent_user_id']
                    agent_cb.setChecked(row_data['agent_checked'])
                    self.setCellWidget(new_row, 5, agent_cb)

                    # VIEWERチェックボックス再作成
                    viewer_cb = QCheckBox()
                    viewer_cb.user_id = row_data['viewer_user_id']
                    viewer_cb.setChecked(row_data['viewer_checked'])
                    self.setCellWidget(new_row, 6, viewer_cb)

                    # 背景色とイベント接続を復元
                    if hasattr(self.parent_selector, 'update_row_background'):
                        # 排他制御を含むハンドラーを作成
                        def create_rebuild_exclusive_handler(row_idx, target_w, other_ws):
                            def handler(checked):
                                if checked:
                                    for w in other_ws:
                                        if hasattr(w, 'setChecked'):
                                            w.setChecked(False)
                                    
                                    # OWNERの場合は他のOWNERラジオボタンも無効化
                                    if isinstance(target_w, QRadioButton):
                                        for other_row in range(self.rowCount()):
                                            if other_row != row_idx:
                                                other_owner = self.cellWidget(other_row, 2)
                                                if other_owner and other_owner != target_w:
                                                    other_owner.setChecked(False)
                                
                                self.parent_selector.update_row_background(row_idx)
                                self.parent_selector.validate_owner_selection()
                            return handler
                        
                        # OWNERラジオボタン専用ハンドラー
                        def create_rebuild_owner_exclusive_handler(row_idx, owner_w, other_ws):
                            def handler(checked):
                                if checked:
                                    # 同一行の他のロールを無効化
                                    for w in other_ws:
                                        if hasattr(w, 'setChecked') and hasattr(w, 'setEnabled'):
                                            w.setChecked(False)
                                            w.setEnabled(False)
                                    
                                    # 他の行のOWNERラジオボタンを無効化
                                    for other_row in range(self.rowCount()):
                                        if other_row != row_idx:
                                            other_owner = self.cellWidget(other_row, 2)
                                            if other_owner and other_owner != owner_w:
                                                other_owner.setChecked(False)
                                else:
                                    # チェック解除時、同一行の他のロールを有効化
                                    for w in other_ws:
                                        if hasattr(w, 'setEnabled'):
                                            w.setEnabled(True)
                                
                                self.parent_selector.update_row_background(row_idx)
                                self.parent_selector.validate_owner_selection()
                            return handler
                        
                        owner_radio.toggled.connect(create_rebuild_owner_exclusive_handler(new_row, owner_radio, [assistant_cb, member_cb, agent_cb, viewer_cb]))
                        assistant_cb.toggled.connect(create_rebuild_exclusive_handler(new_row, assistant_cb, [owner_radio, member_cb, agent_cb, viewer_cb]))
                        member_cb.toggled.connect(create_rebuild_exclusive_handler(new_row, member_cb, [owner_radio, assistant_cb, agent_cb, viewer_cb]))
                        agent_cb.toggled.connect(create_rebuild_exclusive_handler(new_row, agent_cb, [owner_radio, assistant_cb, member_cb, viewer_cb]))
                        viewer_cb.toggled.connect(create_rebuild_exclusive_handler(new_row, viewer_cb, [owner_radio, assistant_cb, member_cb, agent_cb]))

                        self.parent_selector.update_row_background(new_row)
                    
                    print(f"[DEBUG] 行{new_row}再構築完了: {row_data['member_name']}")
                
                # user_rowsリストを再構築
                print(f"[DEBUG] user_rows再構築開始: 元の長さ={len(self.parent_selector.user_rows)}")
                self.parent_selector.user_rows.clear()
                for row in range(self.rowCount()):
                    owner_radio = self.cellWidget(row, 2)
                    assistant_cb = self.cellWidget(row, 3)
                    member_cb = self.cellWidget(row, 4)
                    agent_cb = getattr(self.parent_selector, 'agent_cb', None) or self.cellWidget(row, 5)
                    viewer_cb = getattr(self.parent_selector, 'viewer_cb', None) or self.cellWidget(row, 6)
                    if owner_radio and assistant_cb and member_cb:
                        user_id = getattr(owner_radio, 'user_id', None)
                        # AGENTとVIEWERがない場合はダミーチェックボックスを作成
                        if agent_cb is None:
                            from PyQt5.QtWidgets import QCheckBox
                            agent_cb = QCheckBox()
                            agent_cb.user_id = user_id
                            agent_cb.setChecked(False)
                        if viewer_cb is None:
                            from PyQt5.QtWidgets import QCheckBox
                            viewer_cb = QCheckBox()
                            viewer_cb.user_id = user_id
                            viewer_cb.setChecked(False)
                        self.parent_selector.user_rows.append((user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb))
                        print(f"[DEBUG] 行{row}追加: user_id={user_id}")
                
                print(f"[DEBUG] user_rows再構築完了: 新しい長さ={len(self.parent_selector.user_rows)}")
                # ソートを再有効化
                self.setSortingEnabled(True)
                print(f"[DEBUG] テーブル再構築完了 - user_rows更新: {len(self.parent_selector.user_rows)}行")
        
        table = CustomTableWidget(self)
        table.setColumnCount(7)
        table.setHorizontalHeaderLabels(["メンバー名", "メールアドレス", "管理者", "代理", "メンバ", "登録代行", "閲覧"])
        table.setRowCount(len(self.user_entries))
        table.setSortingEnabled(True)
        
        # テーブルの外枠と内部の余白を完全に削除
        table.setContentsMargins(0, 0, 0, 0)
        table.setFrameStyle(0)  # フレームを削除
        table.setShowGrid(True)  # グリッド線は表示
        
        # テーブルの上下余白を削除するための追加設定
        table.setStyleSheet("""
            QTableWidget {
                border: none;
                margin: 0px;
                padding: 0px;
                background-color: white;
            }
            QTableWidget::item {
                border: none;
                padding: 2px;
            }
        """)
        
        # 列幅調整
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # メンバー名
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # メールアドレス
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # OWNER
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # ASSISTANT
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # MEMBER
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # AGENT
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # VIEWER

        # 行の高さを統一（より小さく設定）
        table.verticalHeader().setDefaultSectionSize(22)  # さらに小さく
        table.verticalHeader().setVisible(False)
        
        # テーブルサイズを動的に計算（画面サイズを考慮）
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        max_table_height = int(screen.height() * 0.6)  # 画面の40%まで
        
        # メンバー数に応じた動的高さ計算
        member_count = len(self.user_entries)
        header_height = 25  # ヘッダーの高さ
        row_height = 22     # 1行の高さ
        calculated_height = header_height + (member_count * row_height)
        
        # 最小・最大値を画面サイズに基づいて設定
        min_height = min(150, max_table_height)
        optimal_height = min(calculated_height, max_table_height)
        
        table.setMinimumHeight(min_height)
        table.setMaximumHeight(optimal_height)
        
        return table
    
    def populate_table(self):
        """テーブルにデータを設定"""
        for row, user in enumerate(self.user_entries):
            # データ構造を統一的に処理
            # 新形式: 直接プロパティ（load_unified_member_list由来）
            if 'userName' in user:
                user_name = user.get('userName', '')
                email = user.get('emailAddress', '')
                user_id = user.get('id', '')
            else:
                # 旧形式: attributes構造
                attr = user.get("attributes", {})
                user_name = attr.get('userName', '')
                email = attr.get('emailAddress', '')
                user_id = user.get("id", "")
            
            # メンバー名
            name_item = QTableWidgetItem(user_name)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 0, name_item)
            
            # メールアドレス
            email_item = QTableWidgetItem(email)
            email_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 1, email_item)
            
            # OWNERラジオボタン
            owner_radio = QRadioButton()
            owner_radio.user_id = user_id
            owner_radio.setChecked(False)
            self.owner_radio_group.addButton(owner_radio)
            self.table.setCellWidget(row, 2, owner_radio)
            
            # ASSISTANTチェックボックス
            assistant_cb = QCheckBox()
            assistant_cb.user_id = user_id
            if user_id in self.prechecked_user_ids:
                assistant_cb.setChecked(True)
            self.table.setCellWidget(row, 3, assistant_cb)
            
            # MEMBERチェックボックス
            member_cb = QCheckBox()
            member_cb.user_id = user_id
            self.table.setCellWidget(row, 4, member_cb)

            # AGENTチェックボックス
            agent_cb = QCheckBox()
            agent_cb.user_id = user_id
            self.table.setCellWidget(row, 5, agent_cb)

            # VIEWERチェックボックス
            viewer_cb = QCheckBox()
            viewer_cb.user_id = user_id
            self.table.setCellWidget(row, 6, viewer_cb)

            # 初期ロール設定（複数ソースから取得）
            existing_role = None
            
            # 1. initial_rolesから取得
            if user_id in self.initial_roles:
                existing_role = self.initial_roles[user_id]
            # 2. ユーザーデータ内のexistingRoleから取得
            elif 'existingRole' in user:
                existing_role = user.get('existingRole')
            
            if existing_role:
                if existing_role == 'OWNER':
                    owner_radio.setChecked(True)
                    assistant_cb.setChecked(False)
                    member_cb.setChecked(False)
                    agent_cb.setChecked(False)
                    viewer_cb.setChecked(False)
                    # OWNERが選択されている場合、同じ行のチェックボックスを無効化
                    assistant_cb.setEnabled(False)
                    member_cb.setEnabled(False)
                    agent_cb.setEnabled(False)
                    viewer_cb.setEnabled(False)
                elif existing_role == 'ASSISTANT':
                    assistant_cb.setChecked(True)
                    owner_radio.setChecked(False)
                    member_cb.setChecked(False)
                    agent_cb.setChecked(False)
                    viewer_cb.setChecked(False)
                elif existing_role == 'MEMBER':
                    member_cb.setChecked(True)
                    owner_radio.setChecked(False)
                    assistant_cb.setChecked(False)
                    viewer_cb.setChecked(False)
                    agent_cb.setChecked(False)
                elif existing_role == 'AGENT':
                    agent_cb.setChecked(True)
                    owner_radio.setChecked(False)
                    assistant_cb.setChecked(False)
                    member_cb.setChecked(False)
                    viewer_cb.setChecked(False)
                elif existing_role == 'VIEWER':
                    viewer_cb.setChecked(True)
                    owner_radio.setChecked(False)
                    assistant_cb.setChecked(False)
                    member_cb.setChecked(False)
                    agent_cb.setChecked(False)

            self.user_rows.append((user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb))
            
            # 排他制御イベント接続
            owner_radio.toggled.connect(lambda checked, r=row: self._on_owner_changed(r, checked))
            assistant_cb.toggled.connect(lambda checked, r=row: self._on_assistant_changed(r, checked))
            member_cb.toggled.connect(lambda checked, r=row: self._on_member_changed(r, checked))
            agent_cb.toggled.connect(lambda checked, r=row: self._on_agent_changed(r, checked))
            viewer_cb.toggled.connect(lambda checked, r=row: self._on_viewer_changed(r, checked))
            # 初期背景色設定
            self.update_row_background(row)
        
        # 初期バリデーション実行
        self.validate_owner_selection()
    
    def _on_owner_changed(self, row, checked):
        """OWNERラジオボタン変更時"""
        assistant_cb = self.table.cellWidget(row, 3)
        member_cb = self.table.cellWidget(row, 4)
        agent_cb = self.table.cellWidget(row, 5)
        viewer_cb = self.table.cellWidget(row, 6)

        if checked:
            # 同一行の他のroleを無効化（チェック解除＋無効化）
            if assistant_cb:
                assistant_cb.setChecked(False)
                assistant_cb.setEnabled(False)  # 無効化
            if member_cb:
                member_cb.setChecked(False)
                member_cb.setEnabled(False)  # 無効化
            if agent_cb:
                agent_cb.setChecked(False)
                agent_cb.setEnabled(False)  # 無効化
            if viewer_cb:
                viewer_cb.setChecked(False)
                viewer_cb.setEnabled(False)  # 無効化
        else:
            # OWNERのチェックが外れた場合、他のチェックボックスを有効化
            if assistant_cb:
                assistant_cb.setEnabled(True)  # 有効化
            if member_cb:
                member_cb.setEnabled(True)  # 有効化
            if agent_cb:
                agent_cb.setEnabled(True)  # 有効化
            if viewer_cb:
                viewer_cb.setEnabled(True)  # 有効化

        self.update_row_background(row)
        self.validate_owner_selection()
    
    def _on_assistant_changed(self, row, checked):
        """ASSISTANTチェックボックス変更時"""
        if checked:
            # 同一行の他のroleを無効化
            owner_radio = self.table.cellWidget(row, 2)
            member_cb = self.table.cellWidget(row, 4)
            agent_cb = self.table.cellWidget(row, 5)
            viewer_cb = self.table.cellWidget(row, 6)

            if owner_radio:
                owner_radio.setChecked(False)
            if member_cb:
                member_cb.setChecked(False)
            if agent_cb:
                agent_cb.setChecked(False)
            if viewer_cb:
                viewer_cb.setChecked(False)
        self.update_row_background(row)
        self.validate_owner_selection()
    
    def _on_member_changed(self, row, checked):
        """MEMBERチェックボックス変更時"""
        if checked:
            # 同一行の他のroleを無効化
            owner_radio = self.table.cellWidget(row, 2)
            assistant_cb = self.table.cellWidget(row, 3)
            agent_cb = self.table.cellWidget(row, 5)
            viewer_cb = self.table.cellWidget(row, 6)

            if owner_radio:
                owner_radio.setChecked(False)
            if assistant_cb:
                assistant_cb.setChecked(False)
            if agent_cb:
                agent_cb.setChecked(False)
            if viewer_cb:
                viewer_cb.setChecked(False)
        self.update_row_background(row)
        self.validate_owner_selection()

    def _on_agent_changed(self, row, checked):
        """AGENTチェックボックス変更時"""
        if checked:
            # 同一行の他のroleを無効化
            owner_radio = self.table.cellWidget(row, 2)
            assistant_cb = self.table.cellWidget(row, 3)
            member_cb = self.table.cellWidget(row, 4)
            viewer_cb = self.table.cellWidget(row, 6)

            if owner_radio:
                owner_radio.setChecked(False)
            if assistant_cb:
                assistant_cb.setChecked(False)
            if member_cb:
                member_cb.setChecked(False)
            if viewer_cb:
                viewer_cb.setChecked(False)
        self.update_row_background(row)

    def _on_viewer_changed(self, row, checked):
        """VIEWERチェックボックス変更時"""
        if checked:
            # 同一行の他のroleを無効化
            owner_radio = self.table.cellWidget(row, 2)
            assistant_cb = self.table.cellWidget(row, 3)
            member_cb = self.table.cellWidget(row, 4)
            agent_cb = self.table.cellWidget(row, 5)

            if owner_radio:
                owner_radio.setChecked(False)
            if assistant_cb:
                assistant_cb.setChecked(False)
            if member_cb:
                member_cb.setChecked(False)
            if agent_cb:
                agent_cb.setChecked(False)
        self.update_row_background(row)

    def update_row_background(self, row):
        """行の背景色を更新"""
        owner_radio = self.table.cellWidget(row, 2)
        assistant_cb = self.table.cellWidget(row, 3)
        member_cb = self.table.cellWidget(row, 4)
        agent_cb = self.table.cellWidget(row, 5)
        viewer_cb = self.table.cellWidget(row, 6)

        if not owner_radio or not assistant_cb or not member_cb or not agent_cb or not viewer_cb:
            return
        
        is_owner = owner_radio.isChecked()
        is_assistant = assistant_cb.isChecked()
        is_member = member_cb.isChecked()
        is_agent = agent_cb.isChecked()
        is_viewer = viewer_cb.isChecked()

        if is_owner:
            # OWNER選択時: より濃い青色
            bg_color = QColor(200, 220, 255)
        elif is_assistant:
            # ASSISTANT選択時: 薄い青色
            bg_color = QColor(230, 240, 255)
        elif is_member:
            # MEMBER選択時: 薄い緑色
            bg_color = QColor(230, 255, 230)
        elif is_agent:
            # AGENT選択時: 薄い黄色
            bg_color = QColor(255, 255, 230)
        elif is_viewer:
            # VIEWER選択時: 薄い灰色
            bg_color = QColor(240, 240, 240)
        else:
            # 未選択時: デフォルト背景色
            bg_color = QColor(255, 255, 255)
        
        # 行全体の背景色を設定
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(bg_color)
    
    def validate_owner_selection(self):
        """OWNER選択の妥当性チェック"""
        owner_count = 0
        for user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb in self.user_rows:
            if owner_radio.isChecked():
                owner_count += 1
        
        # バリデーション結果はログ出力のみ（UIは変更しない）
        if owner_count == 1:
            print("[DEBUG] OWNER選択数正常: 1人")
        else:
            print(f"[DEBUG] OWNER選択数異常: {owner_count}人")
    
    
    def add_user_by_email(self):
        """メールアドレスによるユーザー追加"""
        email = self.email_input.text().strip()
        if not email:
            QMessageBox.warning(self, "入力エラー", "メールアドレスを入力してください。")
            return
        
        # 重複チェック
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            if name_item:
                current_email = name_item.data(Qt.UserRole + 1)  # メールアドレスを格納
                if current_email == email:
                    QMessageBox.information(self, "重複エラー", f"メールアドレス '{email}' は既に追加されています。")
                    return
        
        try:
            # 既存のAPIヘルパーを使用してBearer token取得
            from ..core import subgroup_api_helper
            bearer_token = subgroup_api_helper.find_bearer_token(self)
            
            if not bearer_token:
                QMessageBox.warning(self, "認証エラー", "Bearer tokenが見つかりません。ログインを確認してください。")
                return
            
            # APIでユーザー検索（既存のHTTPヘルパーを使用）
            encoded_email = urllib.parse.quote_plus(email)
            # フィルタパラメータも正しくエンコード
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
            
            if not users:
                QMessageBox.information(self, "ユーザー未発見", f"メールアドレス '{email}' のユーザーが見つかりませんでした。")
                return
            
            # 最初のユーザーを追加
            user = users[0]
            # アクセス例のレスポンス形式に基づいて修正
            user_name = user.get('attributes', {}).get('userName', 'Unknown')
            user_email = user.get('attributes', {}).get('emailAddress', email)
            user_id = user.get('id', '')
            
            # 動的ユーザーデータを作成
            user_data = {
                'id': user_id,
                'userName': user_name,
                'emailAddress': user_email,
                'organizationName': user.get('attributes', {}).get('organizationName', ''),
                'familyName': user.get('attributes', {}).get('familyName', ''),
                'givenName': user.get('attributes', {}).get('givenName', ''),
                'source': 'dynamic'
            }
            
            # 動的ユーザーリストに追加
            if not any(u.get('id') == user_id for u in self.dynamic_users):
                self.dynamic_users.append(user_data)
                print(f"[DEBUG] 動的ユーザーをメモリに追加: {user_name}")
            
            # テーブルに行を追加（add_user_to_table内で一時ファイル保存も実行される）
            self.add_user_to_table(user_name, user_email, user_id)
            
            # 入力フィールドをクリア
            self.email_input.clear()
            
            QMessageBox.information(self, "追加完了", f"ユーザー '{user_name}' を追加しました。")
            
        except Exception as e:
            QMessageBox.critical(self, "API エラー", f"ユーザー検索中にエラーが発生しました:\n{str(e)}")

    def add_user_to_table(self, name, email, user_id):
        """テーブルに新しいユーザーを追加"""
        row_count = self.table.rowCount()
        self.table.setRowCount(row_count + 1)
        
        # 名前列
        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.UserRole, user_id)      # ユーザーIDを格納
        name_item.setData(Qt.UserRole + 1, email)    # メールアドレスを格納
        self.table.setItem(row_count, 0, name_item)
        
        # メール列
        email_item = QTableWidgetItem(email)
        self.table.setItem(row_count, 1, email_item)
        
        # OWNERラジオボタン
        owner_radio = QRadioButton()
        self.table.setCellWidget(row_count, 2, owner_radio)
        
        # ASSISTANTチェックボックス
        assistant_cb = QCheckBox()
        self.table.setCellWidget(row_count, 3, assistant_cb)
        
        # MEMBERチェックボックス
        member_cb = QCheckBox()
        member_cb.setChecked(True)  # デフォルトでMEMBER権限を付与
        self.table.setCellWidget(row_count, 4, member_cb)
        
        # AGENTチェックボックス
        agent_cb = QCheckBox()
        self.table.setCellWidget(row_count, 5, agent_cb)
        
        # VIEWERチェックボックス
        viewer_cb = QCheckBox()
        self.table.setCellWidget(row_count, 6, viewer_cb)
        
        # user_rowsに追加（他のメソッドとの整合性のため）
        if hasattr(self, 'user_rows'):
            self.user_rows.append((user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb))
        
        # 一時ファイルへの保存（メモリとファイルの同期）
        try:
            from ..core import subgroup_api_helper
            # メモリ上のdynamic_usersから該当ユーザーを取得
            matching_user = None
            for user in self.dynamic_users:
                if user.get('id') == user_id:
                    matching_user = user
                    break
            
            if matching_user:
                # 一時ファイルに追加保存
                subgroup_api_helper.add_dynamic_user_to_member_list(matching_user)
            
        except Exception as save_error:
            print(f"[WARNING] 動的ユーザー一時保存エラー: {save_error}")

    def get_selected_roles(self):
        """選択されたユーザーとロールを取得"""
        selected_user_ids = []
        roles = []
        owner_id = None

        for user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb in self.user_rows:
            if owner_radio.isChecked():
                selected_user_ids.append(user_id)
                roles.append({"userId": user_id, "role": "OWNER", "canCreateDatasets": True, "canEditMembers": True})
                owner_id = user_id
            elif assistant_cb.isChecked():
                selected_user_ids.append(user_id)
                roles.append({"userId": user_id, "role": "ASSISTANT", "canCreateDatasets": True, "canEditMembers": False})
            elif member_cb.isChecked():
                selected_user_ids.append(user_id)
                roles.append({"userId": user_id, "role": "MEMBER", "canCreateDatasets": False, "canEditMembers": False})
            elif agent_cb.isChecked():
                selected_user_ids.append(user_id)
                roles.append({"userId": user_id, "role": "AGENT", "canCreateDatasets": False, "canEditMembers": False})
            elif viewer_cb.isChecked():
                selected_user_ids.append(user_id)
                roles.append({"userId": user_id, "role": "VIEWER", "canCreateDatasets": False, "canEditMembers": False})

        return selected_user_ids, roles, owner_id


def create_common_subgroup_member_selector(initial_roles=None, prechecked_user_ids=None):
    """
    共通サブグループメンバー選択ウィジェット作成
    Args:
        initial_roles (dict): user_id -> role のマッピング（修正時に使用）
        prechecked_user_ids (set): 初期選択ユーザーID（新規作成時に使用）
    Returns:
        CommonSubgroupMemberSelector: メンバー選択ウィジェット
    """
    from .subgroup_ui_helpers import load_user_entries
    user_entries = load_user_entries()
    return CommonSubgroupMemberSelector(user_entries, initial_roles, prechecked_user_ids)


def create_common_subgroup_member_selector_with_api_complement(initial_roles=None, prechecked_user_ids=None, subgroup_id=None, bearer_token=None):
    """
    API補完機能付きの共通サブグループメンバー選択ウィジェット作成
    Args:
        initial_roles (dict): user_id -> role のマッピング（修正時に使用）
        prechecked_user_ids (set): 初期選択ユーザーID（新規作成時に使用）
        subgroup_id (str): サブグループID（API補完用）
        bearer_token (str): 認証トークン（API補完用）
    Returns:
        CommonSubgroupMemberSelector: メンバー選択ウィジェット
    """
    # API補完機能を使ってユーザーエントリを取得
    try:
        from ..core import subgroup_api_helper
        
        # Bearer tokenの補完
        if not bearer_token:
            print("[WARNING] create_common_subgroup_member_selector_with_api_complement: bearer_tokenが提供されていません")
        
        # load_unified_member_listを呼び出し（内部でAPI補完が実行される）
        unified_users, member_info = subgroup_api_helper.load_unified_member_list(
            subgroup_id=subgroup_id,
            dynamic_users=None,
            bearer_token=bearer_token
        )
        
        print(f"[DEBUG] API補完付きメンバーセレクター作成: {len(unified_users)}名")
        
        # 統合されたユーザーリストでCommonSubgroupMemberSelectorを作成
        return CommonSubgroupMemberSelector(
            user_entries=unified_users,
            initial_roles=initial_roles,
            prechecked_user_ids=prechecked_user_ids,
            subgroup_id=subgroup_id
        )
        
    except Exception as e:
        print(f"[ERROR] API補完付きメンバーセレクター作成エラー: {e}")
        
        # フォールバック: 通常のメンバーセレクターを作成
        print("[DEBUG] フォールバック: 通常のメンバーセレクターを作成")
        return create_common_subgroup_member_selector(initial_roles, prechecked_user_ids)


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout
    
    app = QApplication(sys.argv)
    
    # テストウィンドウ
    window = QMainWindow()
    window.setWindowTitle("共通サブグループメンバー選択ウィジェット テスト")
    window.resize(800, 600)
    
    # テスト用ウィジェット
    central_widget = QWidget()
    layout = QVBoxLayout()
    
    # 共通メンバー選択ウィジェット作成
    member_selector = create_common_subgroup_member_selector()
    layout.addWidget(member_selector)
    
    # 選択状態表示ボタン
    def show_selection():
        selected_ids, roles, owner_id = member_selector.get_selected_roles()
        print(f"選択されたユーザー: {selected_ids}")
        print(f"ロール情報: {roles}")
        print(f"OWNER: {owner_id}")
    
    test_button = QPushButton("選択状態を表示")
    test_button.clicked.connect(show_selection)
    layout.addWidget(test_button)
    
    central_widget.setLayout(layout)
    window.setCentralWidget(central_widget)
    
    window.show()
    sys.exit(app.exec_())
