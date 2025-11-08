"""
TAGビルダーダイアログ

データセット編集でのTAG設定を支援するダイアログ
- 自由記述入力
- プリセット値からの選択（MI.jsonベース）
- 将来的にAIサジェスト・他データセットからのコピー機能を拡張予定
"""

import json
import os
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel, 
    QListWidget, QListWidgetItem, QTextEdit, QGroupBox, QCheckBox,
    QMessageBox, QScrollArea, QWidget, QSplitter, QLineEdit, QTreeWidget,
    QTreeWidgetItem, QTabWidget, QComboBox
)
from qt_compat.core import Qt, Signal
from qt_compat.gui import QFont


class TagBuilderDialog(QDialog):
    """TAGビルダーダイアログ"""
    
    # TAGが変更されたときのシグナル
    tags_changed = Signal(str)
    
    def __init__(self, parent=None, current_tags=""):
        super().__init__(parent)
        self.current_tags = current_tags
        self.selected_tags = []
        self.preset_data = {}
        
        # プリセットデータを読み込み
        self.load_preset_data()
        
        self.init_ui()
        self.parse_current_tags()
    
    def load_preset_data(self):
        """MI.jsonからプリセットデータを読み込み"""
        try:
            from config.common import INPUT_DIR
            mi_json_path = os.path.join(INPUT_DIR, "ai", "MI.json")
            
            if os.path.exists(mi_json_path):
                print(f"[DEBUG] MI.jsonを読み込み: {mi_json_path}")
                
                with open(mi_json_path, 'r', encoding='utf-8') as f:
                    self.preset_data = json.load(f)
                
                print(f"[DEBUG] プリセットデータ読み込み完了: {len(self.preset_data)}カテゴリ")
                for category, subcategories in self.preset_data.items():
                    if isinstance(subcategories, dict):
                        total_items = sum(len(items) for items in subcategories.values() if isinstance(items, list))
                        print(f"[DEBUG] - {category}: {total_items}項目")
            else:
                print(f"[WARNING] MI.jsonが見つかりません: {mi_json_path}")
                self.set_default_preset_data()
                    
        except Exception as e:
            print(f"[ERROR] MI.json読み込みエラー: {e}")
            self.set_default_preset_data()
    
    def set_default_preset_data(self):
        """デフォルトのプリセットデータを設定"""
        self.preset_data = {
            "基本タグ": {
                "分析手法": [
                    "XRD", "SEM", "TEM", "XPS", "FTIR", "Raman",
                    "AFM", "STM", "NMR", "ESR", "UV-Vis"
                ],
                "材料分類": [
                    "金属", "セラミックス", "ポリマー", "複合材料",
                    "ナノマテリアル", "薄膜", "バルク材料"
                ],
                "処理方法": [
                    "焼成", "焼結", "スパッタリング", "CVD", "PVD",
                    "ゾルゲル", "電析", "機械加工"
                ]
            }
        }
    
    def init_ui(self):
        """UIを初期化"""
        self.setWindowTitle("TAGビルダー")
        self.setModal(True)
        self.resize(800, 600)
        
        # メインレイアウト
        main_layout = QVBoxLayout()
        
        # タブウィジェット
        tab_widget = QTabWidget()
        
        # 1. 自由記述タブ
        free_input_tab = self.create_free_input_tab()
        tab_widget.addTab(free_input_tab, "自由記述")
        
        # 2. プリセットタブ
        preset_tab = self.create_preset_tab()
        tab_widget.addTab(preset_tab, "プリセット選択")
        
        main_layout.addWidget(tab_widget)
        
        # プレビューエリア
        preview_group = QGroupBox("選択されたTAG")
        preview_layout = QVBoxLayout()
        
        self.selected_tags_list = QListWidget()
        self.selected_tags_list.setMaximumHeight(120)
        preview_layout.addWidget(self.selected_tags_list)
        
        # プレビューテキスト
        self.preview_text = QLineEdit()
        self.preview_text.setPlaceholderText("タグがカンマ区切りで表示されます")
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(QLabel("最終出力:"))
        preview_layout.addWidget(self.preview_text)
        
        preview_group.setLayout(preview_layout)
        main_layout.addWidget(preview_group)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        clear_button = QPushButton("クリア")
        clear_button.clicked.connect(self.clear_all_tags)
        button_layout.addWidget(clear_button)
        
        button_layout.addStretch()
        
        cancel_button = QPushButton("キャンセル")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept_tags)
        ok_button.setDefault(True)
        button_layout.addWidget(ok_button)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def create_free_input_tab(self):
        """自由記述タブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 説明
        info_label = QLabel("TAGを自由に入力できます。カンマ区切りで複数のタグを入力してください。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 入力エリア
        self.free_input_edit = QTextEdit()
        self.free_input_edit.setPlaceholderText("例: TEM観察, 電子回折, ナノ構造, 結晶解析")
        self.free_input_edit.setMaximumHeight(150)
        self.free_input_edit.textChanged.connect(self.on_free_input_changed)
        layout.addWidget(self.free_input_edit)
        
        # 追加ボタン
        add_button = QPushButton("入力内容を追加")
        add_button.clicked.connect(self.add_free_input_tags)
        layout.addWidget(add_button)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_preset_tab(self):
        """プリセットタブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 説明
        info_label = QLabel("MI.jsonに基づくプリセットタグから選択できます。大項目・中項目・小項目すべて選択可能です。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 統計情報
        self.stats_label = QLabel()
        self.update_stats_label()
        layout.addWidget(self.stats_label)
        
        # カテゴリ選択
        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("カテゴリ:"))
        
        self.category_combo = QComboBox()
        self.category_combo.currentTextChanged.connect(self.on_category_changed)
        category_layout.addWidget(self.category_combo)
        
        layout.addLayout(category_layout)
        
        # 検索機能
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("検索:"))
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("タグを検索...")
        self.search_edit.textChanged.connect(self.on_search_text_changed)
        search_layout.addWidget(self.search_edit)
        
        clear_search_button = QPushButton("クリア")
        clear_search_button.setMaximumWidth(60)
        clear_search_button.clicked.connect(lambda: self.search_edit.clear())
        search_layout.addWidget(clear_search_button)
        
        layout.addLayout(search_layout)
        
        # ツリービュー
        self.preset_tree = QTreeWidget()
        self.preset_tree.setHeaderLabels(["項目"])
        self.preset_tree.itemChanged.connect(self.on_preset_item_changed)
        self.preset_tree.itemDoubleClicked.connect(self.on_preset_item_double_clicked)
        layout.addWidget(self.preset_tree)
        
        # プリセットデータを表示
        self.populate_preset_data()
        
        widget.setLayout(layout)
        return widget
    
    def update_stats_label(self):
        """統計情報ラベルを更新"""
        if not self.preset_data:
            self.stats_label.setText("プリセットデータなし")
            return
        
        total_categories = len(self.preset_data)
        total_items = 0
        
        for category_data in self.preset_data.values():
            if isinstance(category_data, dict):
                for items in category_data.values():
                    if isinstance(items, list):
                        total_items += len(items)
        
        stats_text = f"利用可能: {total_categories}カテゴリ, {total_items}項目"
        self.stats_label.setText(stats_text)
        self.stats_label.setStyleSheet("color: #666; font-size: 11px;")
    
    def populate_preset_data(self):
        """プリセットデータをツリーに表示"""
        self.category_combo.clear()
        
        if not self.preset_data:
            self.category_combo.addItem("データなし")
            return
        
        # カテゴリを追加
        self.category_combo.addItem("全て表示")
        for category in self.preset_data.keys():
            self.category_combo.addItem(category)
        
        # 全てのデータを表示
        self.update_preset_tree("全て表示")
    
    def on_category_changed(self, category):
        """カテゴリ選択変更時の処理"""
        self.update_preset_tree(category)
    
    def on_search_text_changed(self, search_text):
        """検索テキスト変更時の処理"""
        self.filter_preset_tree(search_text.strip().lower())
    
    def filter_preset_tree(self, search_text):
        """検索テキストに基づいてツリーをフィルター"""
        if not search_text:
            # 検索テキストが空の場合、全て表示
            for i in range(self.preset_tree.topLevelItemCount()):
                self.show_tree_item_recursive(self.preset_tree.topLevelItem(i), True)
            return
        
        # 検索テキストに一致する項目のみ表示
        for i in range(self.preset_tree.topLevelItemCount()):
            category_item = self.preset_tree.topLevelItem(i)
            category_has_match = self.filter_tree_item_recursive(category_item, search_text)
            category_item.setHidden(not category_has_match)
    
    def filter_tree_item_recursive(self, item, search_text):
        """ツリーアイテムを再帰的にフィルター"""
        has_match = False
        
        # 現在のアイテムのテキストをチェック
        item_text = item.text(0).lower()
        current_match = search_text in item_text
        
        # 子アイテムをチェック
        for i in range(item.childCount()):
            child = item.child(i)
            child_has_match = self.filter_tree_item_recursive(child, search_text)
            child.setHidden(not child_has_match)
            
            if child_has_match:
                has_match = True
        
        # 現在のアイテムまたは子にマッチがある場合は表示
        if current_match or has_match:
            item.setHidden(False)
            return True
        else:
            item.setHidden(True)
            return False
    
    def show_tree_item_recursive(self, item, show):
        """ツリーアイテムの表示/非表示を再帰的に設定"""
        item.setHidden(not show)
        for i in range(item.childCount()):
            self.show_tree_item_recursive(item.child(i), show)
    
    def update_preset_tree(self, selected_category):
        """プリセットツリーを更新"""
        self.preset_tree.clear()
        
        if not self.preset_data:
            return
        
        if selected_category == "全て表示":
            categories_to_show = self.preset_data.keys()
        else:
            categories_to_show = [selected_category] if selected_category in self.preset_data else []
        
        for category in categories_to_show:
            category_data = self.preset_data[category]
            if not isinstance(category_data, dict):
                continue
            
            category_item = QTreeWidgetItem([category])
            category_item.setExpanded(True)
            # 大項目も選択可能にする
            category_item.setFlags(category_item.flags() | Qt.ItemIsUserCheckable)
            category_item.setCheckState(0, Qt.Unchecked)
            self.preset_tree.addTopLevelItem(category_item)
            
            for subcategory, items in category_data.items():
                if not isinstance(items, list):
                    continue
                
                subcategory_item = QTreeWidgetItem([subcategory])
                subcategory_item.setExpanded(True)
                # 中項目も選択可能にする
                subcategory_item.setFlags(subcategory_item.flags() | Qt.ItemIsUserCheckable)
                subcategory_item.setCheckState(0, Qt.Unchecked)
                category_item.addChild(subcategory_item)
                
                for item in items:
                    item_widget = QTreeWidgetItem([item])
                    item_widget.setFlags(item_widget.flags() | Qt.ItemIsUserCheckable)
                    item_widget.setCheckState(0, Qt.Unchecked)
                    subcategory_item.addChild(item_widget)
        
        # 現在選択されているタグにチェックを入れる
        self.update_preset_checkboxes()
    
    def update_preset_checkboxes(self):
        """現在のタグ状態に基づいてチェックボックスを更新"""
        for i in range(self.preset_tree.topLevelItemCount()):
            category_item = self.preset_tree.topLevelItem(i)
            self.update_tree_item_checkboxes(category_item)
    
    def update_tree_item_checkboxes(self, item):
        """ツリーアイテムのチェックボックスを再帰的に更新"""
        # 全ての項目（大項目、中項目、小項目）をチェック
        tag_text = item.text(0)
        if tag_text in self.selected_tags:
            item.setCheckState(0, Qt.Checked)
        else:
            item.setCheckState(0, Qt.Unchecked)
        
        # 子アイテムも再帰的にチェック
        for i in range(item.childCount()):
            child = item.child(i)
            self.update_tree_item_checkboxes(child)
    
    def on_preset_item_changed(self, item, column):
        """プリセット項目の選択変更時の処理"""
        tag_text = item.text(0)
        
        if item.checkState(0) == Qt.Checked:
            if tag_text not in self.selected_tags:
                self.selected_tags.append(tag_text)
        else:
            if tag_text in self.selected_tags:
                self.selected_tags.remove(tag_text)
        
        self.update_preview()
    
    def on_preset_item_double_clicked(self, item, column):
        """プリセット項目のダブルクリック時の処理"""
        tag_text = item.text(0)
        
        # ダブルクリックで選択状態を切り替え
        if tag_text in self.selected_tags:
            self.selected_tags.remove(tag_text)
            item.setCheckState(0, Qt.Unchecked)
        else:
            self.selected_tags.append(tag_text)
            item.setCheckState(0, Qt.Checked)
        
        self.update_preview()
    
    def on_free_input_changed(self):
        """自由入力テキスト変更時の処理"""
        # リアルタイムでプレビューは更新しない（追加ボタン押下時のみ）
        pass
    
    def add_free_input_tags(self):
        """自由入力からタグを追加"""
        input_text = self.free_input_edit.toPlainText().strip()
        if not input_text:
            return
        
        # カンマ区切りで分割
        new_tags = [tag.strip() for tag in input_text.split(',') if tag.strip()]
        
        # 重複を避けて追加
        for tag in new_tags:
            if tag not in self.selected_tags:
                self.selected_tags.append(tag)
        
        # 入力欄をクリア
        self.free_input_edit.clear()
        
        # プレビュー更新
        self.update_preview()
        
        # プリセットのチェックボックスも更新
        self.update_preset_checkboxes()
    
    def parse_current_tags(self):
        """現在のタグ文字列を解析してリストに設定"""
        if not self.current_tags:
            return
        
        # カンマ区切りで分割
        tags = [tag.strip() for tag in self.current_tags.split(',') if tag.strip()]
        self.selected_tags = tags
        
        # プレビューを更新
        self.update_preview()
        
        # プリセットのチェックボックスを更新
        self.update_preset_checkboxes()
        
        print(f"[DEBUG] 現在のタグを解析: {tags}")
    
    def update_preview(self):
        """プレビューを更新"""
        # リストウィジェットを更新
        self.selected_tags_list.clear()
        for tag in self.selected_tags:
            item = QListWidgetItem(tag)
            self.selected_tags_list.addItem(item)
        
        # テキストプレビューを更新
        tags_text = ", ".join(self.selected_tags)
        self.preview_text.setText(tags_text)
    
    def clear_all_tags(self):
        """全てのタグをクリア"""
        reply = QMessageBox.question(
            self, "確認", 
            "選択されているタグを全てクリアしますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.selected_tags.clear()
            self.update_preview()
            self.update_preset_checkboxes()
    
    def accept_tags(self):
        """TAGを確定"""
        tags_text = ", ".join(self.selected_tags)
        self.tags_changed.emit(tags_text)
        self.accept()
    
    def get_tags_string(self):
        """タグ文字列を取得"""
        return ", ".join(self.selected_tags)


def test_tag_builder():
    """TAGビルダーのテスト用関数"""
    import sys
    from qt_compat.widgets import QApplication
    
    app = QApplication(sys.argv)
    
    # テスト用の初期タグ
    current_tags = "TEM観察, 電子回折"
    
    dialog = TagBuilderDialog(current_tags=current_tags)
    
    def on_tags_changed(tags):
        print(f"タグが変更されました: {tags}")
    
    dialog.tags_changed.connect(on_tags_changed)
    
    if dialog.exec() == QDialog.Accepted:
        result = dialog.get_tags_string()
        print(f"最終結果: {result}")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    test_tag_builder()
