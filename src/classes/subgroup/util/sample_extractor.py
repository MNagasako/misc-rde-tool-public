"""
サブグループ関連試料抽出機能
"""

import os
import json
import webbrowser
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, 
    QListWidgetItem, QPushButton, QMessageBox, QTextEdit
)
from PyQt5.QtCore import Qt
from config.common import get_samples_dir_path


class RelatedSamplesDialog(QDialog):
    """関連試料表示ダイアログ"""
    
    def __init__(self, subgroup_id, parent=None):
        super().__init__(parent)
        self.subgroup_id = subgroup_id
        self.samples_data = []
        self.init_ui()
        self.load_samples()
    
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
            return
        
        sample_data = current_item.data(Qt.UserRole)
        if not sample_data:
            self.detail_text.clear()
            self.open_link_btn.setEnabled(False)
            return
        
        # 詳細情報の表示
        self.display_sample_details(sample_data)
        self.open_link_btn.setEnabled(True)
    
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


def show_related_samples_dialog(subgroup_id, parent=None):
    """関連試料ダイアログの表示"""
    if not subgroup_id:
        QMessageBox.warning(parent, "エラー", "サブグループIDが指定されていません。")
        return
    
    dialog = RelatedSamplesDialog(subgroup_id, parent)
    dialog.exec_()
