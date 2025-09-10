"""
データ取得2機能のタブウィジェット
画面サイズ適応型レスポンシブデザイン対応
"""

import logging
from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QLineEdit, QApplication,
        QScrollArea, QGroupBox, QGridLayout, QComboBox,
        QTextEdit, QListWidget, QTreeWidget, QTreeWidgetItem,
        QCheckBox, QSpinBox
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass
    class QTabWidget: pass

logger = logging.getLogger(__name__)

class DataFetch2TabWidget(QTabWidget):
    """データ取得2機能のタブウィジェット"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_controller = parent
        self.setup_ui()
        
    def setup_ui(self):
        """UI初期化"""
        if not PYQT5_AVAILABLE:
            return
            
        # レスポンシブデザイン設定
        self.setup_responsive_layout()
        
        # タブ作成
        self.create_search_tab()
        self.create_filter_tab()
        self.create_download_tab()
        
    def setup_responsive_layout(self):
        """レスポンシブレイアウト設定"""
        # 画面サイズ取得
        desktop = QApplication.desktop()
        screen_rect = desktop.screenGeometry()
        screen_width = screen_rect.width()
        
        # レスポンシブ設定
        self.columns = self.get_optimal_layout_columns(screen_width)
        
    def get_optimal_layout_columns(self, width=None):
        """最適な段組数を取得"""
        if width is None:
            desktop = QApplication.desktop()
            width = desktop.screenGeometry().width()
            
        if width < 1024:
            return 1  # 1段組（スクロール表示）
        elif width < 1440:
            return 2  # 2段組（左右分割）
        else:
            return 3  # 3段組（左中右分割）
            
    def create_search_tab(self):
        """検索タブ"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # タイトル
        title_label = QLabel("データ検索")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        content_layout.addWidget(title_label)
        
        # 検索条件グループ
        search_group = QGroupBox("検索条件")
        search_layout = QVBoxLayout(search_group)
        
        # キーワード検索
        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("キーワード:")
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("検索キーワードを入力...")
        keyword_layout.addWidget(keyword_label)
        keyword_layout.addWidget(self.keyword_input)
        search_layout.addLayout(keyword_layout)
        
        # カテゴリ選択
        category_layout = QHBoxLayout()
        category_label = QLabel("カテゴリ:")
        self.category_combo = QComboBox()
        self.category_combo.addItems(["全て", "材料科学", "物理学", "化学", "生物学"])
        category_layout.addWidget(category_label)
        category_layout.addWidget(self.category_combo)
        category_layout.addStretch()
        search_layout.addLayout(category_layout)
        
        # 日付範囲
        date_layout = QHBoxLayout()
        date_label = QLabel("期間:")
        self.date_from_input = QLineEdit()
        self.date_from_input.setPlaceholderText("YYYY-MM-DD")
        self.date_to_input = QLineEdit()
        self.date_to_input.setPlaceholderText("YYYY-MM-DD")
        date_layout.addWidget(date_label)
        date_layout.addWidget(QLabel("開始:"))
        date_layout.addWidget(self.date_from_input)
        date_layout.addWidget(QLabel("終了:"))
        date_layout.addWidget(self.date_to_input)
        date_layout.addStretch()
        search_layout.addLayout(date_layout)
        
        content_layout.addWidget(search_group)
        
        # 検索実行ボタン
        search_execute_group = QGroupBox("検索実行")
        search_execute_layout = QHBoxLayout(search_execute_group)
        
        search_btn = QPushButton("🔍 検索実行")
        search_btn.setMinimumHeight(40)
        search_btn.clicked.connect(self.execute_search)
        search_execute_layout.addWidget(search_btn)
        
        clear_btn = QPushButton("🗑️ 条件クリア")
        clear_btn.setMinimumHeight(40)
        clear_btn.clicked.connect(self.clear_search)
        search_execute_layout.addWidget(clear_btn)
        
        search_execute_layout.addStretch()
        
        content_layout.addWidget(search_execute_group)
        
        # 検索結果表示
        results_group = QGroupBox("検索結果")
        results_layout = QVBoxLayout(results_group)
        
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabels(["タイトル", "カテゴリ", "更新日", "サイズ"])
        self.results_tree.setMaximumHeight(200)
        results_layout.addWidget(self.results_tree)
        
        content_layout.addWidget(results_group)
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.addTab(tab_widget, "データ検索")
        
    def create_filter_tab(self):
        """フィルタタブ"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # タイトル
        title_label = QLabel("高度なフィルタ")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        content_layout.addWidget(title_label)
        
        # ファイル形式フィルタ
        format_group = QGroupBox("ファイル形式")
        format_layout = QVBoxLayout(format_group)
        
        # チェックボックス形式でファイル形式選択
        formats = ["CSV", "JSON", "XML", "TXT", "PDF", "XLSX", "ZIP"]
        self.format_checkboxes = {}
        format_grid = QGridLayout()
        
        for i, fmt in enumerate(formats):
            checkbox = QCheckBox(fmt)
            self.format_checkboxes[fmt] = checkbox
            row = i // 3
            col = i % 3
            format_grid.addWidget(checkbox, row, col)
            
        format_layout.addLayout(format_grid)
        content_layout.addWidget(format_group)
        
        # サイズフィルタ
        size_group = QGroupBox("ファイルサイズ")
        size_layout = QVBoxLayout(size_group)
        
        size_range_layout = QHBoxLayout()
        size_range_layout.addWidget(QLabel("最小:"))
        self.min_size_input = QSpinBox()
        self.min_size_input.setSuffix(" MB")
        self.min_size_input.setMaximum(10000)
        size_range_layout.addWidget(self.min_size_input)
        
        size_range_layout.addWidget(QLabel("最大:"))
        self.max_size_input = QSpinBox()
        self.max_size_input.setSuffix(" MB")
        self.max_size_input.setMaximum(10000)
        self.max_size_input.setValue(1000)
        size_range_layout.addWidget(self.max_size_input)
        
        size_range_layout.addStretch()
        size_layout.addLayout(size_range_layout)
        content_layout.addWidget(size_group)
        
        # アクセス権限フィルタ
        access_group = QGroupBox("アクセス権限")
        access_layout = QVBoxLayout(access_group)
        
        self.public_checkbox = QCheckBox("パブリック")
        self.private_checkbox = QCheckBox("プライベート")
        self.shared_checkbox = QCheckBox("共有")
        
        access_layout.addWidget(self.public_checkbox)
        access_layout.addWidget(self.private_checkbox)
        access_layout.addWidget(self.shared_checkbox)
        
        content_layout.addWidget(access_group)
        
        # フィルタ適用ボタン
        filter_actions_group = QGroupBox("フィルタ操作")
        filter_actions_layout = QHBoxLayout(filter_actions_group)
        
        apply_filter_btn = QPushButton("✅ フィルタ適用")
        apply_filter_btn.setMinimumHeight(40)
        apply_filter_btn.clicked.connect(self.apply_filters)
        filter_actions_layout.addWidget(apply_filter_btn)
        
        reset_filter_btn = QPushButton("🔄 フィルタリセット")
        reset_filter_btn.setMinimumHeight(40)
        reset_filter_btn.clicked.connect(self.reset_filters)
        filter_actions_layout.addWidget(reset_filter_btn)
        
        filter_actions_layout.addStretch()
        
        content_layout.addWidget(filter_actions_group)
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.addTab(tab_widget, "高度なフィルタ")
        
    def create_download_tab(self):
        """ダウンロードタブ"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # スクロールエリア
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # タイトル
        title_label = QLabel("ダウンロード管理")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        content_layout.addWidget(title_label)
        
        # 選択済みアイテム表示
        selected_group = QGroupBox("ダウンロード対象")
        selected_layout = QVBoxLayout(selected_group)
        
        self.selected_list = QListWidget()
        self.selected_list.setMaximumHeight(150)
        selected_layout.addWidget(self.selected_list)
        
        content_layout.addWidget(selected_group)
        
        # ダウンロード設定
        download_settings_group = QGroupBox("ダウンロード設定")
        download_settings_layout = QVBoxLayout(download_settings_group)
        
        # 保存先選択
        save_path_layout = QHBoxLayout()
        save_path_label = QLabel("保存先:")
        self.save_path_input = QLineEdit()
        self.save_path_input.setPlaceholderText("保存先フォルダを選択...")
        browse_btn = QPushButton("📁 参照")
        browse_btn.clicked.connect(self.browse_save_path)
        save_path_layout.addWidget(save_path_label)
        save_path_layout.addWidget(self.save_path_input)
        save_path_layout.addWidget(browse_btn)
        download_settings_layout.addLayout(save_path_layout)
        
        # 同時ダウンロード数
        concurrent_layout = QHBoxLayout()
        concurrent_label = QLabel("同時ダウンロード数:")
        self.concurrent_spinbox = QSpinBox()
        self.concurrent_spinbox.setMinimum(1)
        self.concurrent_spinbox.setMaximum(10)
        self.concurrent_spinbox.setValue(3)
        concurrent_layout.addWidget(concurrent_label)
        concurrent_layout.addWidget(self.concurrent_spinbox)
        concurrent_layout.addStretch()
        download_settings_layout.addLayout(concurrent_layout)
        
        # ZIP圧縮オプション
        self.zip_option_checkbox = QCheckBox("ダウンロード後にZIP圧縮")
        download_settings_layout.addWidget(self.zip_option_checkbox)
        
        content_layout.addWidget(download_settings_group)
        
        # ダウンロード実行ボタン
        download_actions_group = QGroupBox("ダウンロード実行")
        download_actions_layout = QHBoxLayout(download_actions_group)
        
        download_btn = QPushButton("⬇️ ダウンロード開始")
        download_btn.setMinimumHeight(50)
        download_btn.clicked.connect(self.start_download)
        download_actions_layout.addWidget(download_btn)
        
        pause_btn = QPushButton("⏸️ 一時停止")
        pause_btn.clicked.connect(self.pause_download)
        download_actions_layout.addWidget(pause_btn)
        
        cancel_btn = QPushButton("❌ キャンセル")
        cancel_btn.clicked.connect(self.cancel_download)
        download_actions_layout.addWidget(cancel_btn)
        
        download_actions_layout.addStretch()
        
        content_layout.addWidget(download_actions_group)
        
        # ダウンロード進捗表示
        progress_group = QGroupBox("進捗状況")
        progress_layout = QVBoxLayout(progress_group)
        
        self.download_status_label = QLabel("準備完了")
        progress_layout.addWidget(self.download_status_label)
        
        # 進捗詳細
        self.progress_text = QTextEdit()
        self.progress_text.setReadOnly(True)
        self.progress_text.setMaximumHeight(100)
        self.progress_text.setPlaceholderText("ダウンロード進捗がここに表示されます...")
        progress_layout.addWidget(self.progress_text)
        
        content_layout.addWidget(progress_group)
        content_layout.addStretch()
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        self.addTab(tab_widget, "ダウンロード管理")
        
    def execute_search(self):
        """検索実行"""
        try:
            # 検索実行処理
            logger.info("検索を実行しました")
        except Exception as e:
            logger.error(f"検索実行エラー: {e}")
            
    def clear_search(self):
        """検索条件クリア"""
        try:
            self.keyword_input.clear()
            self.category_combo.setCurrentIndex(0)
            self.date_from_input.clear()
            self.date_to_input.clear()
            self.results_tree.clear()
            logger.info("検索条件をクリアしました")
        except Exception as e:
            logger.error(f"検索条件クリアエラー: {e}")
            
    def apply_filters(self):
        """フィルタ適用"""
        try:
            # フィルタ適用処理
            logger.info("フィルタを適用しました")
        except Exception as e:
            logger.error(f"フィルタ適用エラー: {e}")
            
    def reset_filters(self):
        """フィルタリセット"""
        try:
            # 全チェックボックスをクリア
            for checkbox in self.format_checkboxes.values():
                checkbox.setChecked(False)
            self.min_size_input.setValue(0)
            self.max_size_input.setValue(1000)
            self.public_checkbox.setChecked(False)
            self.private_checkbox.setChecked(False)
            self.shared_checkbox.setChecked(False)
            logger.info("フィルタをリセットしました")
        except Exception as e:
            logger.error(f"フィルタリセットエラー: {e}")
            
    def browse_save_path(self):
        """保存先参照"""
        try:
            from PyQt5.QtWidgets import QFileDialog
            folder = QFileDialog.getExistingDirectory(self, "保存先フォルダ選択")
            if folder:
                self.save_path_input.setText(folder)
        except Exception as e:
            logger.error(f"保存先参照エラー: {e}")
            
    def start_download(self):
        """ダウンロード開始"""
        try:
            if self.parent_controller and hasattr(self.parent_controller, 'start_data_fetch'):
                self.parent_controller.start_data_fetch()
        except Exception as e:
            logger.error(f"ダウンロード開始エラー: {e}")
            
    def pause_download(self):
        """ダウンロード一時停止"""
        try:
            # ダウンロード一時停止処理
            logger.info("ダウンロードを一時停止しました")
        except Exception as e:
            logger.error(f"ダウンロード一時停止エラー: {e}")
            
    def cancel_download(self):
        """ダウンロードキャンセル"""
        try:
            # ダウンロードキャンセル処理
            logger.info("ダウンロードをキャンセルしました")
        except Exception as e:
            logger.error(f"ダウンロードキャンセルエラー: {e}")


def create_data_fetch2_tab_widget(parent=None):
    """データ取得2タブウィジェットを作成"""
    try:
        return DataFetch2TabWidget(parent)
    except Exception as e:
        logger.error(f"データ取得2タブウィジェット作成エラー: {e}")
        return None
