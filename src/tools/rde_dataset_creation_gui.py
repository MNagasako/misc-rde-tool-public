#!/usr/bin/env python3
# rde_dataset_creation_gui.py - RDEデータセット開設調査GUI
# PyQt5によるGUI付きHTTPリクエスト調査ツール
# 目的：サブグループ作成→データセット開設の操作をGUIで実行・記録

import sys
import os
# パス管理システムを使用（CWD非依存）
# 注意: モジュールパスの設定は共通設定で管理
import json

from datetime import datetime
from typing import Dict, Any, Optional, TYPE_CHECKING
from qt_compat.widgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTextEdit, QComboBox, QGroupBox, QTabWidget,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QMessageBox, QFileDialog, QCheckBox, QSpinBox,
                             QDialog, QDialogButtonBox)
from qt_compat.core import Qt, QTimer
from qt_compat.gui import QFont, QTextCursor
from classes.theme import get_color, ThemeKey

# パス設定（上記で一元化）

from tools.rde_request_analyzer import RDERequestAnalyzer
from config.common import OUTPUT_LOG_DIR
from core.bearer_token_manager import BearerTokenManager


try:
    from tools.classes.password_auth_dialog import PasswordAuthDialog
except ModuleNotFoundError:
    from classes.password_auth_dialog import PasswordAuthDialog


try:
    from tools.classes.request_thread import RequestThread
except ModuleNotFoundError:
    from classes.request_thread import RequestThread



# --- モジュールパス調整: src直下を常にimport可能に ---
import os
import sys
# パス管理システムを使用（CWD非依存）
from config.common import get_static_resource_path, get_dynamic_file_path

class RDEDatasetCreationGUI(QMainWindow):
    """RDEデータセット開設調査GUI"""
    
    def __init__(self, parent_webview=None, parent_controller=None):
        super().__init__()
        self.parent_webview = parent_webview
        self.parent_controller = parent_controller
        self.analyzer = RDERequestAnalyzer(log_to_file=True)
        self.request_history = []
        self.current_request_thread = None
        self.webview_navigation_log = []
        
        # 画面解像度を取得して動的にサイズ調整
        self.setup_dynamic_sizing()
        
        # GUI初期化
        self.init_ui()
        
        # Cookie自動読み込み（WebViewから取得するか、ファイルから読み込み）
        self.load_cookies_from_webview_or_file()
        
        # 認証ヘッダーを自動設定
        self.refresh_auth_headers()
        
        # Bearerトークンファイルの初期チェック
        self.check_initial_auth_status()
    
    def _style_label(self, label: QLabel, color_str: str, bold: bool = False, point_size: int | None = None):
        """QLabelへフォント+パレットでスタイル適用 (QSS削減)"""
        try:
            font = label.font()
            if point_size is not None:
                font.setPointSize(point_size)
            font.setBold(bold)
            label.setFont(font)
            pal = label.palette()
            pal.setColor(label.foregroundRole(), QColor(color_str))
            label.setPalette(pal)
        except Exception:
            try:
                label.setStyleSheet(f"color: {color_str};")
            except Exception:
                pass
    
    def setup_dynamic_sizing(self):
        """画面解像度に応じて動的にサイズとフォントを調整"""
        from qt_compat.widgets import QApplication
        
        # 画面サイズを取得
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        screen_width = screen_size.width()
        screen_height = screen_size.height()
        
        # 解像度に応じたサイズ設定（全画面に近いサイズ）
        if screen_width >= 1920 and screen_height >= 1080:  # フルHD以上
            self.window_width = int(screen_width * 0.9)  # 画面の90%
            self.window_height = int(screen_height * 0.85)  # 画面の85%
            self.button_font_size = 10
            self.text_font_size = 9
            self.code_font_size = 9
        elif screen_width >= 1366 and screen_height >= 768:  # 一般的なラップトップ
            self.window_width = int(screen_width * 0.9)  # 画面の90%
            self.window_height = int(screen_height * 0.85)  # 画面の85%
            self.button_font_size = 9
            self.text_font_size = 8
            self.code_font_size = 8
        else:  # 小さい画面（1024x768など）
            self.window_width = int(screen_width * 0.95)  # 画面の95%
            self.window_height = int(screen_height * 0.9)  # 画面の90%
            self.button_font_size = 8
            self.text_font_size = 7
            self.code_font_size = 7
        
        # ウィンドウサイズ設定（中央に配置）
        x = (screen_width - self.window_width) // 2
        y = (screen_height - self.window_height) // 2
        self.setGeometry(x, y, self.window_width, self.window_height)
        self.setMinimumSize(int(self.window_width * 0.7), int(self.window_height * 0.7))
    
    def create_styled_button(self, text, color_style="default"):
        """スタイル付きボタンを作成（StyledButtonFactoryへ委譲）"""
        try:
            from tools.classes.styled_button_factory import StyledButtonFactory
        except ModuleNotFoundError:
            from classes.styled_button_factory import StyledButtonFactory
        return StyledButtonFactory.create_styled_button(text, color_style, self.button_font_size)
    
    def init_ui(self):
        """GUI初期化"""
        title = "RDE Dataset Creation Analyzer - v1.0"
        if self.parent_webview is not None:
            title += " (WebView連携)"
        self.setWindowTitle(title)
        # 低解像度画面でも使いやすいサイズに調整 (1024x768でも使用可能)
        self.setGeometry(50, 50, 1000, 700)
        self.setMinimumSize(800, 600)
        
        # 全体的なフォントサイズを設定（低解像度でも見やすく）
        font = QFont()
        font.setPointSize(9)  # 基本フォントサイズを9ptに
        self.setFont(font)
        
        # 中央ウィジェット
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # メインレイアウト
        main_layout = QVBoxLayout(central_widget)
        
        # タブウィジェット
        tab_widget = QTabWidget()
        # タブフォントを明確に設定
        tab_font = QFont()
        tab_font.setPointSize(10)
        tab_font.setBold(True)
        tab_widget.setFont(tab_font)
        main_layout.addWidget(tab_widget)
        
        # タブ1: リクエスト送信
        self.request_tab = self.create_request_tab()
        tab_widget.addTab(self.request_tab, "リクエスト送信")
        
        # タブ2: ダミー操作選択
        self.dummy_tab = self.create_dummy_tab()
        tab_widget.addTab(self.dummy_tab, "ダミー操作選択")
        
        # タブ3: 履歴・ログ
        self.history_tab = self.create_history_tab()
        tab_widget.addTab(self.history_tab, "履歴・ログ")
        
        # ステータスバー
        self.statusBar().showMessage("Ready")
    

    def create_request_tab(self) -> "QWidget":
        """リクエスト送信タブ作成（左右分割・独立スクロール対応）"""
        from qt_compat.widgets import QScrollArea, QSizePolicy, QGridLayout, QSplitter

        # スプリッターで左右分割
        splitter = QSplitter()
        splitter.setOrientation(Qt.Horizontal)

        # --- 左カラム（コマンド・入力欄：ラベル・グループ名の重複を排除し、必要最小限に） ---
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_widget = QWidget()
        left_scroll.setWidget(left_widget)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(12)
        left_layout.setContentsMargins(12, 10, 12, 10)

        # --- ボタン群の最大幅を計算し、左カラムの推奨幅を決定 ---
        # 各グループの最大列数に合わせて幅を計算
        left_min_width = 0
        # ユーザー: 2列, データセット: 3列, グループ: 3列, 検索: 1列
        button_width = 130
        button_margin = 4  # padding+marginの合計
        user_cols = 2
        dataset_cols = 3
        group_cols = 3
        action_cols = 1
        # グループ間の余白も考慮
        group_spacing = 24
        left_min_width = max(
            user_cols * (button_width + button_margin),
            dataset_cols * (button_width + button_margin),
            group_cols * (button_width + button_margin),
            action_cols * (button_width + button_margin)
        ) + 48  # グループボックスの余白分
        # さらに左カラムの他要素の余白も加味
        left_min_width += 32

        # スクロールバーが出ないように左側の最小幅を設定
        left_scroll.setMinimumWidth(left_min_width)
        left_scroll.setMaximumWidth(left_min_width + 40)
        left_widget.setMinimumWidth(left_min_width)
        left_widget.setMaximumWidth(left_min_width + 40)

        # HTTPメソッド選択（ラベルのみ、グループ名なし）
        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("メソッド:"))
        self.method_combo = QComboBox()
        self.method_combo.addItems(["GET", "POST", "PUT", "DELETE", "PATCH"])
        method_row.addWidget(self.method_combo)
        method_row.addStretch()
        left_layout.addLayout(method_row)

        # URL入力（ラベルのみ、グループ名なし）
        url_row = QVBoxLayout()
        url_label = QLabel("URL:")
        url_label.setFont(QFont("Arial", 10, QFont.Bold))
        url_row.addWidget(url_label)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://rde-user-api.nims.go.jp/users/self")
        self.url_input.setMinimumWidth(300)
        self.url_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        url_row.addWidget(self.url_input)
        left_layout.addLayout(url_row)

        # プリセットボタン群（種類ごとにグルーピング）
        from qt_compat.widgets import QGroupBox
        # ボタン共通サイズ・スタイル
        button_width = 130
        button_height = 32
        button_style = "padding:2px 8px; margin:2px; min-width:{}px; min-height:{}px; max-width:{}px; max-height:{}px;".format(button_width, button_height, button_width, button_height)

        from qt_compat.widgets import QGridLayout

        # ユーザー系
        user_group = QGroupBox("ユーザーAPI")
        user_grid = QGridLayout(user_group)
        user_btns = [
            ("ユーザー情報", "user", lambda: self.setup_simple_get_request("https://rde-user-api.nims.go.jp/users/self")),
            ("プロフィール", "user", lambda: self.setup_simple_get_request("https://rde-user-api.nims.go.jp/users/profile")),
        ]
        for i, (text, color, cb) in enumerate(user_btns):
            btn = self.create_styled_button(text, color)
            btn.clicked.connect(cb)
            btn.setFixedSize(button_width, button_height)
            btn.setStyleSheet(btn.styleSheet() + ";" + button_style)
            user_grid.addWidget(btn, i // 2, i % 2)
        left_layout.addWidget(user_group)

        # データセット系
        dataset_group = QGroupBox("データセットAPI")
        dataset_grid = QGridLayout(dataset_group)
        dataset_btns = [
            ("データセット一覧", "dataset", lambda: self.setup_simple_get_request("https://rde-api.nims.go.jp/datasets")),
            ("データセット詳細", "dataset", lambda: self.setup_dataset_detail_request()),
            ("データセット作成", "dataset", lambda: self.setup_create_dataset_request()),
            ("メタデータ", "action", lambda: self.setup_simple_get_request("https://rde-api.nims.go.jp/datasets/{id}/metadata")),
            ("権限情報", "action", lambda: self.setup_simple_get_request("https://rde-api.nims.go.jp/datasets/{id}/permissions")),
        ]
        for i, (text, color, cb) in enumerate(dataset_btns):
            btn = self.create_styled_button(text, color)
            btn.clicked.connect(cb)
            btn.setFixedSize(button_width, button_height)
            btn.setStyleSheet(btn.styleSheet() + ";" + button_style)
            dataset_grid.addWidget(btn, i // 3, i % 3)
        left_layout.addWidget(dataset_group)

        # グループ系
        group_group = QGroupBox("グループAPI")
        group_grid = QGridLayout(group_group)
        group_btns = [
            ("グループ一覧", "group", lambda: self.setup_simple_get_request("https://rde-api.nims.go.jp/groups")),
            ("グループ詳細", "group", lambda: self.setup_group_detail_request()),
            ("グループルート", "web", lambda: self.setup_web_get_request("https://rde.nims.go.jp/rde/datasets/groups/root")),
            ("グループAPI(root)", "api", lambda: self.setup_simple_get_request("https://rde-api.nims.go.jp/groups/root?include=children%2Cmembers")),
            ("サブグループAPI", "api", lambda: self.setup_simple_get_request("https://rde-api.nims.go.jp/groups/4bbf62be-f270-4a46-9682-38cd064607ba?include=children%2Cmembers")),
            ("東北大学API", "group", lambda: self.setup_simple_get_request("https://rde-api.nims.go.jp/groups/1af3d7dd-bea8-4508-84dc-6990cd8c6753?include=children%2Cmembers")),
            ("東北大学WEB", "web", lambda: self.setup_web_get_request("https://rde.nims.go.jp/rde/datasets/groups/1af3d7dd-bea8-4508-84dc-6990cd8c6753")),
            ("サブグループ作成", "action", lambda: self.setup_create_subgroup_request()),
        ]
        for i, (text, color, cb) in enumerate(group_btns):
            btn = self.create_styled_button(text, color)
            btn.clicked.connect(cb)
            btn.setFixedSize(button_width, button_height)
            btn.setStyleSheet(btn.styleSheet() + ";" + button_style)
            group_grid.addWidget(btn, i // 3, i % 3)
        left_layout.addWidget(group_group)

        # 検索・操作系
        action_group = QGroupBox("検索・操作API")
        action_grid = QGridLayout(action_group)
        action_btns = [
            ("データセット検索", "action", lambda: self.setup_search_request()),
        ]
        for i, (text, color, cb) in enumerate(action_btns):
            btn = self.create_styled_button(text, color)
            btn.clicked.connect(cb)
            btn.setFixedSize(button_width, button_height)
            btn.setStyleSheet(btn.styleSheet() + ";" + button_style)
            action_grid.addWidget(btn, i, 0)
        left_layout.addWidget(action_group)

        # 認証ヘッダー自動設定（ラベルのみ）
        auth_row = QHBoxLayout()
        auth_row.addWidget(QLabel("認証ステータス:"))
        self.auth_status_label = QLabel("未設定")
        self._style_label(self.auth_status_label, get_color(ThemeKey.STATUS_ERROR), bold=True)
        auth_row.addWidget(self.auth_status_label)
        self.refresh_auth_button = self.create_styled_button("認証情報更新", "default")
        self.refresh_auth_button.clicked.connect(self.refresh_auth_headers)
        auth_row.addWidget(self.refresh_auth_button)
        auth_row.addStretch()
        left_layout.addLayout(auth_row)

        # 実行ボタン
        button_layout = QHBoxLayout()
        try:
            from tools.classes.widget_factory import create_action_button
        except ModuleNotFoundError:
            from classes.widget_factory import create_action_button
        self.execute_button = create_action_button("リクエスト実行", self.execute_request, color_style="default", font_size=self.button_font_size + 1)
        self.clear_button = create_action_button("クリア", self.clear_request_form, color_style="default", font_size=self.button_font_size)
        self.merge_token_button = create_action_button("Bearer Token追加", self.merge_bearer_token_to_headers, color_style="auth", font_size=self.button_font_size)
        self.execute_button.setMinimumWidth(120)
        self.clear_button.setMinimumWidth(100)
        self.merge_token_button.setMinimumWidth(140)
        button_layout.addWidget(self.execute_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.merge_token_button)
        button_layout.addStretch()
        left_layout.addLayout(button_layout)

        left_layout.addStretch()

        # --- 右カラム（出力・レスポンス・テキストエリア類を集約） ---
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_widget = QWidget()
        right_scroll.setWidget(right_widget)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setSpacing(12)
        right_layout.setContentsMargins(12, 10, 12, 10)

        # ヘッダー入力
        try:
            from tools.classes.widget_factory import create_labeled_textedit
        except ModuleNotFoundError:
            from classes.widget_factory import create_labeled_textedit
        headers_label, self.headers_input = create_labeled_textedit(
            "ヘッダー (JSON形式):",
            '{"Accept": "application/vnd.api+json", "Authorization": "Bearer token", "Origin": "https://rde.nims.go.jp"}',
            max_height=100
        )
        right_layout.addWidget(headers_label)
        right_layout.addWidget(self.headers_input)

        # データ入力
        form_label, self.form_data_input = create_labeled_textedit(
            "フォームデータ (JSON形式):",
            '{"key": "value", "field": "data"}',
            max_height=100
        )
        json_label, self.json_data_input = create_labeled_textedit(
            "JSONデータ:",
            '{"message": "hello", "data": {"key": "value"}}',
            max_height=100
        )
        right_layout.addWidget(form_label)
        right_layout.addWidget(self.form_data_input)
        right_layout.addWidget(json_label)
        right_layout.addWidget(self.json_data_input)

        # URLパラメータ
        params_label, self.params_input = create_labeled_textedit(
            "URLパラメータ (JSON形式):",
            '{"page": "1", "limit": "10"}',
            max_height=60
        )
        right_layout.addWidget(params_label)
        right_layout.addWidget(self.params_input)

        # レスポンス表示エリア
        response_header_row = QHBoxLayout()
        self.response_status_label = QLabel("ステータス: 未実行")
        self._style_label(self.response_status_label, get_color(ThemeKey.TEXT_MUTED), bold=True)
        self.response_time_label = QLabel("実行時間: -")
        self.response_size_label = QLabel("サイズ: -")
        response_header_row.addWidget(self.response_status_label)
        response_header_row.addWidget(self.response_time_label)
        response_header_row.addWidget(self.response_size_label)
        response_header_row.addStretch()
        right_layout.addLayout(response_header_row)

        self.response_display = QTextEdit()
        self.response_display.setReadOnly(True)
        response_font = QFont("Consolas", self.code_font_size)
        if not response_font.exactMatch():
            response_font = QFont("Courier New", self.code_font_size)
        self.response_display.setFont(response_font)
        self.response_display.setPlaceholderText("リクエスト実行後にレスポンス内容が表示されます...")
        self.response_display.setMaximumHeight(300)
        self.response_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout.addWidget(self.response_display)

        # レスポンス操作ボタン
        response_button_layout = QHBoxLayout()
        self.copy_response_button = create_action_button("レスポンスをコピー", self.copy_response_to_clipboard, color_style="default")
        self.copy_response_button.setEnabled(False)
        self.save_response_button = create_action_button("レスポンスを保存", self.save_response_to_file, color_style="default")
        self.save_response_button.setEnabled(False)
        self.clear_response_button = create_action_button("レスポンスクリア", self.clear_response_display, color_style="action")
        self.copy_response_button.setMinimumWidth(120)
        self.save_response_button.setMinimumWidth(120)
        self.clear_response_button.setMinimumWidth(120)
        response_button_layout.addWidget(self.copy_response_button)
        response_button_layout.addWidget(self.save_response_button)
        response_button_layout.addWidget(self.clear_response_button)
        response_button_layout.addStretch()
        right_layout.addLayout(response_button_layout)

        right_layout.addStretch()

        splitter.addWidget(left_scroll)
        splitter.addWidget(right_scroll)

        # ボタン群の高さを計算して左カラムの高さを確定させる（初期表示時に右と左のバランスを最適化）
        left_scroll.adjustSize()
        left_widget.adjustSize()
        left_width = left_widget.sizeHint().width()
        right_width = right_widget.sizeHint().width()
        # 右側は残り幅を自動で使う
        total_width = self.window_width if hasattr(self, 'window_width') else 1400
        # 左右比率を計算
        left_final = max(left_width, left_min_width)
        right_final = max(total_width - left_final, 400)
        splitter.setSizes([left_final, right_final])

        return splitter
        

    
    def copy_response_to_clipboard(self):
        """レスポンス内容をクリップボードにコピー"""
        try:
            if hasattr(self, 'current_response_data'):
                formatted_content = self.format_response_for_display(self.current_response_data)
                
                from qt_compat.widgets import QApplication
                clipboard = QApplication.clipboard()
                clipboard.setText(formatted_content)
                
                self.statusBar().showMessage("レスポンス内容をクリップボードにコピーしました", 3000)
                self.log_message("レスポンス内容をクリップボードにコピー完了")
            else:
                QMessageBox.warning(self, "コピーエラー", "コピーするレスポンスデータがありません")
        except Exception as e:
            QMessageBox.critical(self, "コピーエラー", f"クリップボードへのコピーに失敗しました: {e}")
    
    def save_response_to_file(self):
        """レスポンス内容を個別ファイルに保存"""
        try:
            if not hasattr(self, 'current_response_data'):
                QMessageBox.warning(self, "保存エラー", "保存するレスポンスデータがありません")
                return
            
            # ファイル名生成
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            method = self.current_response_data.get('request', {}).get('method', 'UNKNOWN')
            
            default_filename = f"response_{timestamp}_{method}.txt"
            
            filename = QFileDialog.getSaveFileName(
                self, "レスポンス保存", 
                os.path.join(self.create_request_log_folder(), default_filename),
                "Text files (*.txt);;JSON files (*.json);;All files (*)"
            )[0]
            
            if filename:
                # ファイル拡張子に応じて形式を決定
                if filename.lower().endswith('.json'):
                    # JSON形式で保存
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(self.current_response_data, f, indent=2, ensure_ascii=False)
                else:
                    # テキスト形式で保存（整形済み）
                    formatted_content = self.format_response_for_display(self.current_response_data)
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(formatted_content)
                
                QMessageBox.information(self, "保存完了", f"レスポンスを保存しました:\n{filename}")
                self.log_message(f"レスポンス個別ファイル保存: {filename}")
                
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", f"レスポンス保存に失敗しました: {e}")
    
    def clear_response_display(self):
        """レスポンス表示エリアをクリア"""
        try:
            self.response_display.clear()
            self.response_status_label.setText("ステータス: 未実行")
            self._style_label(self.response_status_label, get_color(ThemeKey.TEXT_MUTED), bold=True)
            self.response_time_label.setText("実行時間: -")
            self.response_size_label.setText("サイズ: -")
            
            # ボタン無効化
            self.copy_response_button.setEnabled(False)
            self.save_response_button.setEnabled(False)
            
            # レスポンスデータクリア
            if hasattr(self, 'current_response_data'):
                delattr(self, 'current_response_data')
                
        except Exception as e:
            self.log_message(f"レスポンスクリア エラー: {e}")
    
    def format_response_for_display(self, result: Dict) -> str:
        """レスポンスを表示用に整形（ResponseFormatterへ委譲）"""
        try:
            from tools.classes.response_formatter import ResponseFormatter
        except ModuleNotFoundError:
            from classes.response_formatter import ResponseFormatter
        return ResponseFormatter.format_response_for_display(result)
    
    
    def create_dummy_tab(self) -> "QWidget":
        """ダミー操作選択タブ作成（widget_factory利用版）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # --- widget_factoryのimport（try/exceptで両対応） ---
        try:
            from tools.classes.widget_factory import create_action_button, create_labeled_lineedit
        except ModuleNotFoundError:
            from classes.widget_factory import create_action_button, create_labeled_lineedit

        # 操作選択
        operation_group = QGroupBox("RDEデータセット開設操作")
        operation_layout = QVBoxLayout(operation_group)

        # Phase 1: サブグループ作成
        phase1_group = QGroupBox("Phase 1: サブグループ作成")
        phase1_layout = QVBoxLayout(phase1_group)

        self.create_subgroup_button = create_action_button("サブグループ作成リクエスト", self.dummy_create_subgroup, color_style="group")
        self.add_members_button = create_action_button("グループメンバー登録リクエスト", self.dummy_add_members, color_style="group")

        phase1_layout.addWidget(self.create_subgroup_button)
        phase1_layout.addWidget(self.add_members_button)

        # Phase 2: データセット開設
        phase2_group = QGroupBox("Phase 2: データセット開設")
        phase2_layout = QVBoxLayout(phase2_group)

        self.create_dataset_button = create_action_button("データセット開設リクエスト", self.dummy_create_dataset, color_style="dataset")
        self.setup_dataset_button = create_action_button("データセット設定リクエスト", self.dummy_setup_dataset, color_style="dataset")

        phase2_layout.addWidget(self.create_dataset_button)
        phase2_layout.addWidget(self.setup_dataset_button)

        operation_layout.addWidget(phase1_group)
        operation_layout.addWidget(phase2_group)

        layout.addWidget(operation_group)

        # 設定項目
        settings_group = QGroupBox("ダミーデータ設定")
        settings_layout = QVBoxLayout(settings_group)

        # サブグループ名
        subgroup_label, self.subgroup_name_input = create_labeled_lineedit(
            "サブグループ名:",
            "test_subgroup_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        )
        # データセット名
        dataset_label, self.dataset_name_input = create_labeled_lineedit(
            "データセット名:",
            "test_dataset_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        )

        settings_layout.addWidget(subgroup_label)
        settings_layout.addWidget(self.subgroup_name_input)
        settings_layout.addWidget(dataset_label)
        settings_layout.addWidget(self.dataset_name_input)

        layout.addWidget(settings_group)

        # 自動実行
        auto_group = QGroupBox("自動実行")
        auto_layout = QVBoxLayout(auto_group)

        self.auto_execute_button = create_action_button("全工程自動実行", self.auto_execute_all, color_style="action", font_size=self.button_font_size + 2)
        auto_layout.addWidget(self.auto_execute_button)

        layout.addWidget(auto_group)

        layout.addStretch()

        return widget
    
    def create_history_tab(self) -> "QWidget":
        """履歴・ログタブ作成"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # --- widget_factoryのimport（try/exceptで両対応） ---
        try:
            from tools.classes.widget_factory import create_labeled_textedit
        except ModuleNotFoundError:
            from classes.widget_factory import create_labeled_textedit

        # ログ表示
        log_group = QGroupBox("リクエスト・レスポンスログ")
        log_layout = QVBoxLayout(log_group)
        log_label, self.log_display = create_labeled_textedit(
            "ログ:", "", max_height=200
        )
        self.log_display.setReadOnly(True)
        log_font = QFont("Consolas", self.code_font_size)
        self.log_display.setFont(log_font)
        log_layout.addWidget(log_label)
        log_layout.addWidget(self.log_display)
        layout.addWidget(log_group)
        
        # 履歴テーブル
        history_group = QGroupBox("リクエスト履歴")
        history_layout = QVBoxLayout(history_group)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["時刻", "メソッド", "URL", "ステータス", "レスポンス時間"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        history_layout.addWidget(self.history_table)
        
        layout.addWidget(history_group)
        
        # 操作ボタン
        button_layout = QHBoxLayout()
        
        self.save_log_button = self.create_styled_button("ログ保存", "default")
        self.save_log_button.clicked.connect(self.save_log)
        
        self.clear_log_button = self.create_styled_button("ログクリア", "action")
        self.clear_log_button.clicked.connect(self.clear_log)
        
        button_layout.addWidget(self.save_log_button)
        button_layout.addWidget(self.clear_log_button)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        return widget
    
    def load_cookies(self):
        """Cookie読み込み"""
        try:
            success = self.analyzer.load_cookies()
            if success:
                self.statusBar().showMessage("Cookie読み込み成功")
                self.log_message("Cookie読み込み成功")
            else:
                self.statusBar().showMessage("Cookie読み込み失敗")
                self.log_message("Cookie読み込み失敗")
        except Exception as e:
            self.statusBar().showMessage(f"Cookie読み込みエラー: {e}")
            self.log_message(f"Cookie読み込みエラー: {e}")
    
    def load_cookies_from_webview_or_file(self):
        """WebViewまたはファイルからCookie読み込み"""
        if self.parent_webview is not None:
            self.load_cookies_from_webview()
        else:
            self.load_cookies()
    
    def load_cookies_from_webview(self):
        """親WebViewからCookie情報を取得してHTTPクライアントに設定"""
        try:
            from qt_compat.webengine import QWebEngineProfile
            from qt_compat.webengine import QWebEngineCookieStore
            from net import http as requests  # プロキシ対応HTTP wrapper
            
            # WebViewのProfileからCookieStoreを取得
            if hasattr(self.parent_webview, 'page'):
                profile = self.parent_webview.page().profile()
                cookie_store = profile.cookieStore()
                
                # 現在のドメインのCookieを取得（実装は複雑なため、フォールバック）
                current_url = self.parent_webview.url().toString() if self.parent_webview.url() else ""
                
                self.log_message(f"WebViewから Cookie情報を取得中... (URL: {current_url})")
                
                # WebView連携の代替手段：既存のCookieファイルを使用
                success = self.analyzer.load_cookies()
                if success:
                    self.statusBar().showMessage("WebView連携 - Cookie読み込み成功")
                    self.log_message("WebView連携でCookie読み込み成功")
                    
                    # URLフィールドに現在のWebViewのURLをプリセット
                    if current_url and hasattr(self, 'url_input'):
                        base_url = current_url.split('?')[0]  # クエリパラメータを除去
                        self.url_input.setText(base_url)
                        self.log_message(f"URLフィールドにWebViewのURL設定: {base_url}")
                else:
                    self.load_cookies()  # フォールバック
            else:
                self.log_message("WebView情報が無効です。ファイルからCookie読み込みを実行")
                self.load_cookies()
                
        except Exception as e:
            self.log_message(f"WebView Cookie取得エラー: {e}")
            self.statusBar().showMessage(f"WebView Cookie取得エラー: {e}")
            # フォールバックとして通常のCookie読み込み
            self.load_cookies()
    
    def refresh_auth_headers(self):
        """WebViewから認証ヘッダーを自動取得・設定"""
        return self.get_bearer_token()

 
    

    def check_initial_auth_status(self):
        """初期認証ステータスチェック"""
        try:
            bearer_token = self.get_bearer_token()
            if bearer_token:
                # トークンの有効期限をチェック（JWTの場合）
                try:
                    import json
                    import base64
                    
                    # JWTの場合、ペイロード部分をデコード
                    parts = bearer_token.split('.')
                    if len(parts) >= 2:
                        # Base64デコード（パディング調整）
                        payload = parts[1]
                        payload += '=' * (4 - len(payload) % 4)
                        decoded = base64.urlsafe_b64decode(payload)
                        jwt_data = json.loads(decoded)
                        
                        # 有効期限チェック
                        if 'exp' in jwt_data:
                            import time
                            exp_time = jwt_data['exp']
                            current_time = time.time()
                            
                            if exp_time > current_time:
                                remaining_hours = (exp_time - current_time) / 3600
                                self.log_message(f"Bearerトークン有効期限確認: 残り約{remaining_hours:.1f}時間")
                                return True
                            else:
                                self.log_message("警告: Bearerトークンの有効期限が切れています")
                                self.update_auth_status("トークン期限切れ")
                                return False
                                
                except Exception as jwt_error:
                    self.log_message(f"JWTデコードエラー（処理続行）: {jwt_error}")
                
                self.log_message("Bearerトークンファイル検出済み - 認証準備完了")
                return True
            else:
                self.log_message("Bearerトークンファイル未検出 - ログインが必要です")
                self.update_auth_status("ログイン必要")
                return False
                
        except Exception as e:
            self.log_message(f"初期認証ステータスチェックエラー: {e}")
            return False
    
    def sync_webview_cookies(self):
        """WebViewのCookieをHTTPクライアントに同期"""
        try:
            if self.parent_webview is not None:
                # WebViewのCookieをHTTPセッションに設定
                profile = self.parent_webview.page().profile()
                current_url = self.parent_webview.url().toString()
                
                # 既存のアナライザーにWebViewのセッション状態を同期
                if hasattr(self.analyzer, 'session'):
                    # User-Agentを同期
                    user_agent = profile.httpUserAgent()
                    self.analyzer.session.headers.update({
                        'User-Agent': user_agent
                    })
                    
                    # CookieをJavaScriptで取得してHTTPセッションに設定
                    js_cookie_code = """
                    (function() {
                        return document.cookie;
                    })();
                    """
                    
                    def handle_cookies(cookie_string):
                        try:
                            if cookie_string:
                                # CookieをHTTPセッションに設定
                                from net import http as requests  # プロキシ対応HTTP wrapper
                                cookie_jar = requests.cookies.RequestsCookieJar()
                                
                                # Cookie文字列を解析してcookie_jarに追加
                                rde_cookies = []
                                for cookie in cookie_string.split(';'):
                                    if '=' in cookie:
                                        name, value = cookie.strip().split('=', 1)
                                        rde_cookies.append(f"{name}={value}")
                                        # ドメインを設定（RDEの複数ドメインに対応）
                                        for domain in ['.nims.go.jp', '.rde.nims.go.jp', 'rde.nims.go.jp', 'rde-api.nims.go.jp', 'rde-user-api.nims.go.jp']:
                                            cookie_jar.set(name, value, domain=domain, path='/')
                                
                                self.analyzer.session.cookies.update(cookie_jar)
                                
                                # Cookieを詳細ログ出力
                                self.log_message(f"WebView Cookie詳細:")
                                for i, cookie_info in enumerate(rde_cookies[:10]):  # 最初の10個を表示
                                    self.log_message(f"  Cookie {i+1}: {cookie_info[:80]}...")
                                
                                self.log_message(f"WebView Cookie同期: {len(cookie_jar)}個のCookieを設定")
                                
                                # 特定の認証系Cookieをチェック
                                auth_cookies = ['session', 'auth', 'token', 'jwt', 'access_token', 'refresh_token']
                                for cookie_name in auth_cookies:
                                    if cookie_name in cookie_string:
                                        self.log_message(f"認証関連Cookie検出: {cookie_name}")
                                        
                        except Exception as e:
                            self.log_message(f"Cookie同期エラー: {e}")
                    
                    # JavaScriptを実行してCookieを取得
                    self.parent_webview.page().runJavaScript(js_cookie_code, handle_cookies)
                
                self.log_message(f"WebViewセッション同期完了: {current_url}")
                
        except Exception as e:
            self.log_message(f"WebViewセッション同期エラー: {e}")
    
    def setup_fallback_auth_headers(self, auth_headers, current_url):
        """フォールバック認証ヘッダー設定"""
        try:
            # Bearerトークンがまだ設定されていない場合、ファイルから読み込み
            if 'Authorization' not in auth_headers:
                bearer_token = self.get_bearer_token()
                if bearer_token:
                    auth_headers['Authorization'] = f"Bearer {bearer_token}"
                    self.log_message(f"フォールバック処理でBearerトークン設定: {bearer_token[:30]}...")
            
            # RDE API専用のHTTPヘッダー設定（正しい例に基づく）
            fallback_headers = {
                'Accept': 'application/vnd.api+json',
                'Content-Type': 'application/vnd.api+json;charset=utf-8',
                'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Origin': 'https://rde.nims.go.jp',
                'Referer': 'https://rde.nims.go.jp/',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            }
            
            # 動的URLベースの設定調整
            if current_url:
                # WebViewから取得したURLの場合は、そのURLをRefererに使用
                fallback_headers['Referer'] = current_url
                
                # URLからOriginを設定（RDE関連ドメインの場合）
                from urllib.parse import urlparse
                parsed = urlparse(current_url)
                if 'rde.nims.go.jp' in parsed.netloc:
                    fallback_headers['Origin'] = 'https://rde.nims.go.jp'
                elif 'rde-api.nims.go.jp' in parsed.netloc:
                    fallback_headers['Origin'] = 'https://rde.nims.go.jp'
                elif 'rde-user-api.nims.go.jp' in parsed.netloc:
                    fallback_headers['Origin'] = 'https://rde.nims.go.jp'
                else:
                    fallback_headers['Origin'] = f"{parsed.scheme}://{parsed.netloc}"
            
            # 既存の認証ヘッダーにフォールバック値を追加（重複を避ける）
            for key, value in fallback_headers.items():
                if key not in auth_headers:
                    auth_headers[key] = value
            
            self.log_message(f"RDE API専用ヘッダー設定完了: {len(fallback_headers)}個のヘッダーを追加")
            
            # CSRFトークンをCookieから取得（フォールバック）
            if hasattr(self.analyzer, 'get_csrf_token'):
                try:
                    # CSRFトークンを取得（URLパラメータが必要な場合）
                    csrf_token = self.analyzer.get_csrf_token(current_url or "https://rde.nims.go.jp")
                    if csrf_token and 'X-CSRF-TOKEN' not in auth_headers:
                        #auth_headers['X-CSRF-TOKEN'] = csrf_token
                        #auth_headers['X-Requested-With'] = 'XMLHttpRequest'
                        self.log_message(f"CSRFトークン設定成功: {csrf_token[:20]}...")
                    else:
                        # CSRFトークンが見つからない場合の代替処理
                        self.log_message("CSRFトークンが見つかりません - セッションベース認証を使用")
                        
                        # セッションベース認証のヘッダーを設定
                        session_headers = {
                            'X-Requested-With': 'XMLHttpRequest',
                            'Accept': 'application/json, text/plain, */*',
                            'Cache-Control': 'no-cache',
                            'Pragma': 'no-cache'
                        }
                        
                        # RefererとOriginを現在のURLから設定
                        if current_url:
                            base_url = '/'.join(current_url.split('/')[:3])
                            session_headers['Referer'] = current_url
                            session_headers['Origin'] = base_url
                        
                        auth_headers.update(session_headers)
                        self.log_message("セッションベース認証ヘッダーを設定しました")
                        
                except Exception as csrf_error:
                    self.log_message(f"CSRF取得エラー（フォールバック処理続行）: {csrf_error}")
                    
                    # エラー時もセッションベース認証を設定
                    fallback_headers = {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json, text/plain, */*'
                    }
                    auth_headers.update(fallback_headers)
            
        except Exception as e:
            self.log_message(f"フォールバック認証設定エラー: {e}")
    
    def apply_auth_headers(self, auth_headers):
        """認証ヘッダーをGUIに適用"""
        try:
            if auth_headers:
                # 既存のヘッダー入力と統合
                existing_headers = self.parse_json_input(self.headers_input.toPlainText()) or {}
                
                # 認証ヘッダーを追加/更新
                existing_headers.update(auth_headers)
                
                # ヘッダー入力フィールドに設定
                headers_json = json.dumps(existing_headers, indent=2, ensure_ascii=False)
                self.headers_input.setText(headers_json)
                
                # ステータス更新
                auth_status = "認証完了"
                if 'Authorization' in auth_headers:
                    auth_status += " (Bearer)"
                if 'X-CSRF-TOKEN' in auth_headers:
                    auth_status += " + CSRF"
                if self.parent_webview is not None:
                    auth_status += " + WebView連携"
                    
                self.update_auth_status(auth_status)
                
                self.log_message(f"認証ヘッダー設定完了: {len(auth_headers)}個のヘッダーを適用")
                
            else:
                # Bearerトークンファイルの確認
                bearer_token = self.get_bearer_token()
                if bearer_token:
                    self.update_auth_status("Bearerトークンファイル検出")
                else:
                    self.update_auth_status("認証情報なし")
                
        except Exception as e:
            self.log_message(f"認証ヘッダー適用エラー: {e}")
            self.update_auth_status("設定エラー")
    
    def update_auth_status(self, status):
        """認証ステータス表示を更新"""
        try:
            if hasattr(self, 'auth_status_label'):
                self.auth_status_label.setText(status)
                
                if "完了" in status:
                    self._style_label(self.auth_status_label, get_color(ThemeKey.STATUS_SUCCESS), bold=True)
                elif "エラー" in status or "なし" in status:
                    self._style_label(self.auth_status_label, get_color(ThemeKey.STATUS_ERROR), bold=True)
                else:
                    self._style_label(self.auth_status_label, get_color(ThemeKey.STATUS_WARNING), bold=True)
                    
        except Exception as e:
            self.log_message(f"認証ステータス更新エラー: {e}")
    
    def execute_request(self):
        """リクエスト実行（WebViewインスタンス連携・認証ヘッダー自動更新）"""
        if self.current_request_thread and self.current_request_thread.isRunning():
            QMessageBox.warning(self, "警告", "他のリクエストが実行中です。")
            return
        
        try:
            # 認証ヘッダーを最新状態に更新
            self.refresh_auth_headers()
            
            # WebViewと同じURLに更新（同じインスタンスで通信）
            if self.parent_webview is not None:
                target_url = self.url_input.text().strip()
                if target_url:
                    self.update_webview_to_url(target_url)
            
            # 入力値取得
            method = self.method_combo.currentText()
            url = self.url_input.text().strip()
            
            if not url:
                QMessageBox.warning(self, "エラー", "URLを入力してください。")
                return
            
            # URL検証（改良版）
            is_valid, validation_message = self.validate_url(url)
            
            if not is_valid:
                QMessageBox.warning(self, "URL検証エラー", validation_message)
                return
            elif validation_message:  # 警告がある場合
                reply = QMessageBox.question(
                    self, "URL警告", 
                    f"{validation_message}\n\n続行しますか？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
            
            # レスポンス表示エリアをクリア
            self.clear_response_display()
            self.response_status_label.setText("ステータス: 実行中...")
            self._style_label(self.response_status_label, get_color(ThemeKey.STATUS_WARNING), bold=True)
            
            # WebViewのセッション状態をログ出力
            self.log_webview_session_info()
            
            # JSON解析
            headers = self.parse_json_input(self.headers_input.toPlainText())
            form_data = self.parse_json_input(self.form_data_input.toPlainText())
            json_data = self.parse_json_input(self.json_data_input.toPlainText())
            params = self.parse_json_input(self.params_input.toPlainText())
            
            # 送信前のヘッダーデバッグ表示
            self.log_message(f"=== 送信ヘッダー詳細 ===")
            if headers:
                for key, value in headers.items():
                    if key.lower() == 'authorization' and value:
                        # Bearerトークンは最初の部分のみ表示
                        display_value = f"{value[:20]}..." if len(value) > 20 else value
                        self.log_message(f"  {key}: {display_value}")
                    else:
                        self.log_message(f"  {key}: {value}")
            else:
                self.log_message("  ヘッダーが設定されていません")
            self.log_message(f"=== リクエスト送信: {method} {url} ===")
            
            # 実行開始時刻を記録
            self.request_start_time = datetime.now()
            
            # スレッドでリクエスト実行
            self.current_request_thread = RequestThread(
                self.analyzer, method, url, headers, form_data, params, json_data
            )
            self.current_request_thread.request_completed.connect(self.on_request_completed)
            self.current_request_thread.start()
            
            self.execute_button.setEnabled(False)
            self.execute_button.setText("実行中...")
            self.statusBar().showMessage("リクエスト実行中...")
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"リクエスト実行エラー: {e}")
            self.response_status_label.setText("ステータス: エラー")
            self._style_label(self.response_status_label, get_color(ThemeKey.STATUS_ERROR), bold=True)
    
    def update_webview_to_url(self, target_url):
        """WebViewを指定URLに移動（同じインスタンスで通信確保）"""
        try:
            if self.parent_webview is not None:
                current_url = self.parent_webview.url().toString()
                
                # 同じドメインかチェック
                from urllib.parse import urlparse
                current_domain = urlparse(current_url).netloc if current_url else ""
                target_domain = urlparse(target_url).netloc
                
                # RDEの関連ドメイン判定
                rde_domains = ['rde.nims.go.jp', 'rde-api.nims.go.jp', 'rde-user-api.nims.go.jp']
                current_is_rde = any(domain in current_domain for domain in rde_domains)
                target_is_rde = any(domain in target_domain for domain in rde_domains)
                
                if current_domain == target_domain:
                    # 同じドメインなら直接移動
                    from qt_compat.core import QUrl
                    self.parent_webview.setUrl(QUrl(target_url))
                    self.log_message(f"WebView移動: {target_url}")
                elif current_is_rde and target_is_rde:
                    # 両方ともRDE関連ドメインの場合は警告のみ（移動はしない）
                    self.log_message(f"RDE関連ドメイン間リクエスト: {current_domain} → {target_domain}")
                    self.log_message("WebViewのログイン状態を維持してAPIアクセス実行")
                else:
                    # 完全に異なるドメインの場合は警告
                    self.log_message(f"警告: 異なるドメインへのリクエスト (現在: {current_domain}, 対象: {target_domain})")
                
        except Exception as e:
            self.log_message(f"WebView URL更新エラー: {e}")
    
    def log_webview_session_info(self):
        """WebViewのセッション情報をログ出力"""
        try:
            if self.parent_webview is not None:
                current_url = self.parent_webview.url().toString()
                user_agent = self.parent_webview.page().profile().httpUserAgent()
                
                session_info = {
                    "webview_url": current_url,
                    "user_agent": user_agent[:100] + "..." if len(user_agent) > 100 else user_agent,
                    "timestamp": datetime.now().isoformat()
                }
                
                self.log_message(f"WebViewセッション情報: {json.dumps(session_info, indent=2, ensure_ascii=False)}")
                
        except Exception as e:
            self.log_message(f"WebViewセッション情報取得エラー: {e}")
    
    def parse_json_input(self, text: str) -> Optional[Dict]:
        """JSON入力解析"""
        text = text.strip()
        if not text:
            return None
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "JSON解析エラー", f"JSON形式が正しくありません: {e}")
            return None
    
    def on_request_completed(self, result: Dict):
        """リクエスト完了時の処理（詳細レスポンス表示・ファイル保存付き）"""
        self.execute_button.setEnabled(True)
        self.execute_button.setText("リクエスト実行")
        
        # 実行時間計算
        if hasattr(self, 'request_start_time'):
            execution_time = datetime.now() - self.request_start_time
            execution_ms = execution_time.total_seconds() * 1000
            self.response_time_label.setText(f"実行時間: {execution_ms:.0f}ms")
        
        # レスポンス詳細表示
        self.display_full_response(result)
        
        # 結果表示（ログエリア用）
        self.display_request_result(result)
        
        # 履歴追加
        self.add_to_history(result)
        
        # ファイル保存
        saved_file = self.save_request_result_to_file(result)
        if saved_file:
            self.log_message(f"詳細結果ファイル保存: {saved_file}")
        
        self.statusBar().showMessage("リクエスト完了")
    
    def display_full_response(self, result: Dict):
        """レスポンス詳細を専用エリアに表示"""
        try:
            # ステータス表示更新
            if 'response' in result:
                response_info = result['response']
                status_code = response_info.get('status_code', 'Unknown')
                status_text = response_info.get('status_text', '')
                
                # ステータスコードに応じて色分け
                if isinstance(status_code, int):
                    if 200 <= status_code < 300:
                        status_color = get_color(ThemeKey.STATUS_SUCCESS)  # 成功 (緑)
                    elif 300 <= status_code < 400:
                        status_color = get_color(ThemeKey.STATUS_WARNING)  # リダイレクト (オレンジ)
                    elif 400 <= status_code < 500:
                        status_color = get_color(ThemeKey.STATUS_ERROR)  # クライアントエラー (赤)
                    else:
                        status_color = get_color(ThemeKey.STATUS_ERROR)  # サーバーエラー (濃い赤)
                else:
                    status_color = get_color(ThemeKey.TEXT_MUTED)
                
                status_display = f"{status_code}"
                if status_text:
                    status_display += f" {status_text}"
                
                self.response_status_label.setText(f"ステータス: {status_display}")
                self._style_label(self.response_status_label, status_color, bold=True)
                
                # レスポンスサイズ計算
                body = response_info.get('body', '')
                if isinstance(body, dict):
                    body_size = len(json.dumps(body, ensure_ascii=False))
                else:
                    body_size = len(str(body))
                
                if body_size > 1024:
                    size_display = f"{body_size / 1024:.1f} KB"
                else:
                    size_display = f"{body_size} bytes"
                
                self.response_size_label.setText(f"サイズ: {size_display}")
                
            else:
                self.response_status_label.setText("ステータス: エラー (レスポンスなし)")
                self._style_label(self.response_status_label, get_color(ThemeKey.STATUS_ERROR), bold=True)
                self.response_size_label.setText("サイズ: -")
            
            # レスポンス内容表示（フル表示・整形済み）
            display_content = self.format_response_for_display(result)
            self.response_display.setText(display_content)
            
            # ボタン有効化
            self.copy_response_button.setEnabled(True)
            self.save_response_button.setEnabled(True)
            
            # 保存用にレスポンスデータを保持
            self.current_response_data = result
            
        except Exception as e:
            self.log_message(f"レスポンス表示エラー: {e}")
            self.response_display.setText(f"レスポンス表示エラー: {e}")
    
    def format_response_for_display(self, result: Dict) -> str:
        """レスポンスを表示用に整形"""
        try:
            formatted_parts = []
            
            # リクエスト情報
            if 'request' in result:
                req = result['request']
                formatted_parts.append("=== REQUEST ===")
                formatted_parts.append(f"Method: {req.get('method', 'Unknown')}")
                formatted_parts.append(f"URL: {req.get('url', 'Unknown')}")
                
                if 'headers' in req and req['headers']:
                    formatted_parts.append("\nRequest Headers:")
                    for key, value in req['headers'].items():
                        if key.lower() == 'authorization' and value:
                            formatted_parts.append(f"  {key}: {value[:20]}... (truncated)")
                        else:
                            formatted_parts.append(f"  {key}: {value}")
                
                if 'data' in req and req['data']:
                    formatted_parts.append(f"\nRequest Data: {json.dumps(req['data'], indent=2, ensure_ascii=False)}")
                
                formatted_parts.append("")
            
            # レスポンス情報
            if 'response' in result:
                resp = result['response']
                formatted_parts.append("=== RESPONSE ===")
                formatted_parts.append(f"Status: {resp.get('status_code', 'Unknown')}")
                formatted_parts.append(f"URL: {resp.get('url', 'Unknown')}")
                
                if 'headers' in resp and resp['headers']:
                    formatted_parts.append("\nResponse Headers:")
                    for key, value in resp['headers'].items():
                        formatted_parts.append(f"  {key}: {value}")
                
                if 'body' in resp:
                    formatted_parts.append("\nResponse Body:")
                    body = resp['body']
                    if isinstance(body, dict):
                        formatted_parts.append(json.dumps(body, indent=2, ensure_ascii=False))
                    else:
                        formatted_parts.append(str(body))
            
            # エラー情報
            if 'error' in result:
                formatted_parts.append("\n=== ERROR ===")
                formatted_parts.append(str(result['error']))
            
            # タイムスタンプ
            if 'timestamp' in result:
                formatted_parts.append(f"\n=== TIMESTAMP ===")
                formatted_parts.append(result['timestamp'])
            
            return "\n".join(formatted_parts)
            
        except Exception as e:
            return f"フォーマット処理エラー: {e}\n\n元データ:\n{json.dumps(result, indent=2, ensure_ascii=False)}"
    
    def display_request_result(self, result: Dict):
        """リクエスト結果表示（HistoryLoggerへ委譲）"""
        try:
            from tools.classes.history_logger import HistoryLogger
        except ModuleNotFoundError:
            from classes.history_logger import HistoryLogger
        HistoryLogger.display_request_result(self.log_display, result)
    
    def add_to_history(self, result: Dict):
        """履歴テーブルに追加（HistoryLoggerへ委譲）"""
        try:
            from tools.classes.history_logger import HistoryLogger
        except ModuleNotFoundError:
            from classes.history_logger import HistoryLogger
        HistoryLogger.add_to_history(self.request_history, self.history_table, result)
    
    def log_message(self, message: str):
        """ログメッセージ表示"""
        self.log_display.append(message)
        
        # 最下部にスクロール
        cursor = self.log_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)  # PySide6: MoveOperation列挙型
        self.log_display.setTextCursor(cursor)
    
    def clear_request_form(self):
        """リクエストフォームとレスポンス表示をクリア"""
        self.url_input.clear()
        self.headers_input.clear()
        self.form_data_input.clear()
        self.json_data_input.clear()
        self.params_input.clear()
        
        # レスポンス表示もクリア
        self.clear_response_display()
    
    def clear_log(self):
        """ログクリア（HistoryLoggerへ委譲）"""
        try:
            from tools.classes.history_logger import HistoryLogger
        except ModuleNotFoundError:
            from classes.history_logger import HistoryLogger
        HistoryLogger.clear_log(self.log_display, self.request_history, self.history_table)
    
    def save_log(self):
        """ログ保存（LogSaverへ委譲）"""
        try:
            try:
                from tools.classes.log_saver import LogSaver
            except ModuleNotFoundError:
                from classes.log_saver import LogSaver
            LogSaver.save_log(self, self.request_history, OUTPUT_LOG_DIR, self.log_message)
        except Exception as e:
            from qt_compat.widgets import QMessageBox
            QMessageBox.critical(self, "保存エラー", f"ログ保存エラー: {e}")
            self.log_message(f"ログ保存エラー: {e}")
    
    def save_request_result_to_file(self, result):
        """リクエスト結果をファイルに保存（RequestSaverへ委譲）"""
        try:
            try:
                from tools.classes.request_saver import RequestSaver
            except ModuleNotFoundError:
                from classes.request_saver import RequestSaver
            filename = RequestSaver.save_request_result_to_file(result)
            if filename is None:
                self.log_message("ファイル保存エラー: 保存に失敗しました")
            return filename
        except Exception as e:
            self.log_message(f"ファイル保存エラー: {e}")
            return None
    
    def setup_create_dataset_request(self):
        """データセット作成リクエストの設定"""
        self.method_combo.setCurrentText("POST")
        self.url_input.setText("https://rde-api.nims.go.jp/datasets")
        
        # JSONデータのテンプレートを設定
        template_data = {
            "data": {
                "type": "datasets",
                "attributes": {
                    "title": "新しいデータセット",
                    "description": "データセットの説明",
                    "access_level": "private",
                    "data_type": "research_data"
                }
            }
        }
        
        self.json_data_input.setText(json.dumps(template_data, indent=2, ensure_ascii=False))
        self.log_message("データセット作成リクエストテンプレートを設定しました")
    
    def setup_search_request(self):
        """データセット検索リクエストの設定（パラメータのみ設定）"""
        self.method_combo.setCurrentText("GET")
        # URLはシンプルに設定
        self.url_input.setText("https://rde-api.nims.go.jp/datasets")
        
        # URLパラメータのみを設定（重複を避ける）
        web_headers={
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Content-Type": "application/vnd.api+json",
            "Host": "rde-api.nims.go.jp",
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\""
        }

        search_params = {
            "searchWords": "JPMXP1222TU0195"
        }

        # Bearerトークンを自動で取得・マージ
        bearer_token = self.get_bearer_token()
        if bearer_token:
            web_headers["Authorization"] = f"Bearer {bearer_token}"

        self.headers_input.setPlainText(json.dumps(web_headers, indent=2))
        self.params_input.setText(json.dumps(search_params, indent=2, ensure_ascii=False))
        self.log_message("データセット検索リクエストテンプレートを設定しました")
    
    def dummy_create_subgroup(self):
        """ダミー：サブグループ作成"""
        self.log_message("ダミー操作: サブグループ作成")
        
        # ダミーリクエスト設定
        self.method_combo.setCurrentText("POST")
        self.url_input.setText("https://rde.nii.ac.jp/api/subgroup/create")
        
        dummy_data = {
            "name": self.subgroup_name_input.text(),
            "description": "Test subgroup for dataset creation",
            "members": ["user1@example.com", "user2@example.com"]
        }
        
        self.json_data_input.setText(json.dumps(dummy_data, indent=2, ensure_ascii=False))
        
        # 自動実行
        QTimer.singleShot(1000, self.execute_request)
    
    def dummy_add_members(self):
        """ダミー：グループメンバー登録"""
        self.log_message("ダミー操作: グループメンバー登録")
        
        self.method_combo.setCurrentText("POST")
        self.url_input.setText("https://rde.nii.ac.jp/api/subgroup/members/add")
        
        dummy_data = {
            "subgroup_id": "dummy_subgroup_id",
            "members": [
                {"email": "new_member1@example.com", "role": "member"},
                {"email": "new_member2@example.com", "role": "admin"}
            ]
        }
        
        self.json_data_input.setText(json.dumps(dummy_data, indent=2, ensure_ascii=False))
        
        QTimer.singleShot(1000, self.execute_request)
    
    def dummy_create_dataset(self):
        """ダミー：データセット開設"""
        self.log_message("ダミー操作: データセット開設")
        # ポップアップ表示ロジックを呼び出し
        try:
            from tools.dataset_create_logic import show_dataset_create_popup
        except ImportError:
            from dataset_create_logic import show_dataset_create_popup
        show_dataset_create_popup()  # 親ウィジェット無しで表示

    
    def setup_dataset_detail_request(self):
        """データセット詳細リクエストの設定（パラメータなし）"""
        self.method_combo.setCurrentText("GET")
        # パラメータを含むサンプルURLを設定
        sample_url = "https://rde-api.nims.go.jp/datasets/f4c08af8-4a74-406d-bcad-04649e8d0d78"
        self.url_input.setText(sample_url)
        
        # 詳細取得用のパラメータを設定
        detail_params = {
            "updateViews": "true",
            "include": "releases,applicant,program,manager,relatedDatasets,template,instruments,license,sharingGroups",
            "fields[release]": "id,releaseNumber,version,doi,note,releaseTime",
            "fields[user]": "id,userName,organizationName,isDeleted",
            "fields[group]": "id,name",
            "fields[datasetTemplate]": "id,nameJa,nameEn,version,datasetType,isPrivate,workflowEnabled",
            "fields[instrument]": "id,nameJa,nameEn,status",
            "fields[license]": "id,url,fullName"
        }
        
        self.params_input.setText(json.dumps(detail_params, indent=2, ensure_ascii=False))
        self.log_message("データセット詳細リクエストテンプレートを設定しました（実際のIDに置換してください）")
    
    def dummy_setup_dataset(self):
        """ダミー：データセット設定"""
        self.log_message("ダミー操作: データセット設定")
        
        self.method_combo.setCurrentText("PUT")
        self.url_input.setText("https://rde.nii.ac.jp/api/dataset/setup")
        
        dummy_data = {
            "dataset_id": "dummy_dataset_id",
            "metadata": {
                "keywords": ["research", "data", "analysis"],
                "license": "CC BY 4.0",
                "language": "ja"
            },
            "permissions": {
                "read": ["subgroup_members"],
                "write": ["subgroup_admins"],
                "delete": ["owner"]
            }
        }
        
        self.json_data_input.setText(json.dumps(dummy_data, indent=2, ensure_ascii=False))
        
        QTimer.singleShot(1000, self.execute_request)
    
    def auto_execute_all(self):
        """全工程自動実行"""
        self.log_message("=== 全工程自動実行開始 ===")
        
        # 順次実行のためのタイマー設定
        QTimer.singleShot(1000, self.dummy_create_subgroup)
        QTimer.singleShot(5000, self.dummy_add_members)
        QTimer.singleShot(10000, self.dummy_create_dataset)
        QTimer.singleShot(15000, self.dummy_setup_dataset)
        
        QTimer.singleShot(20000, lambda: self.log_message("=== 全工程自動実行完了 ==="))
    
    def log_webview_navigation(self, url, action):
        """WebViewのナビゲーション情報をログに記録"""
        try:
            timestamp = datetime.now().isoformat()
            navigation_info = {
                "timestamp": timestamp,
                "url": url,
                "action": action,
                "type": "webview_navigation"
            }
            
            self.webview_navigation_log.append(navigation_info)
            
            # GUI のログエリアに表示
            log_message = f"[WebView {action}] {url}"
            self.log_message(log_message)
            
            # ナビゲーション履歴タブがあれば更新
            self.update_navigation_history()
            
            print(f"WebView監視: {action} - {url}")
            
        except Exception as e:
            print(f"WebViewナビゲーションログエラー: {e}")
    
    def update_navigation_history(self):
        """ナビゲーション履歴を更新"""
        try:
            # 履歴・ログタブの3番目のタブ（WebViewナビゲーション）を更新
            if hasattr(self, 'history_tabs') and self.history_tabs.count() >= 3:
                nav_widget = self.history_tabs.widget(2)  # 3番目のタブ
                if nav_widget and hasattr(nav_widget, 'findChild'):
                    nav_table = nav_widget.findChild(QTableWidget)
                    if nav_table:
                        nav_table.setRowCount(len(self.webview_navigation_log))
                        
                        for i, nav_info in enumerate(self.webview_navigation_log):
                            nav_table.setItem(i, 0, QTableWidgetItem(nav_info["timestamp"]))
                            nav_table.setItem(i, 1, QTableWidgetItem(nav_info["action"]))
                            nav_table.setItem(i, 2, QTableWidgetItem(nav_info["url"]))
                        
                        # 最新の行を表示
                        if len(self.webview_navigation_log) > 0:
                            nav_table.scrollToBottom()
            
        except Exception as e:
            print(f"ナビゲーション履歴更新エラー: {e}")
    
    def create_navigation_history_widget(self):
        """WebViewナビゲーション履歴ウィジェットを作成"""
        # --- widget_factoryのimport（try/exceptで両対応） ---
        try:
            from tools.classes.widget_factory import create_action_button
        except ModuleNotFoundError:
            from classes.widget_factory import create_action_button

        widget = QWidget()
        layout = QVBoxLayout()

        # 説明ラベル
        desc_label = QLabel("WebViewでの画面遷移を自動記録")
        self._style_label(desc_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
        layout.addWidget(desc_label)

        # ナビゲーション履歴テーブル
        nav_table = QTableWidget()
        nav_table.setColumnCount(3)
        nav_table.setHorizontalHeaderLabels(["時刻", "アクション", "URL"])

        # カラム幅調整
        header = nav_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)

        layout.addWidget(nav_table)

        # クリアボタン（widget_factory経由で作成）
        clear_button = create_action_button("履歴クリア", self.clear_navigation_history)
        layout.addWidget(clear_button)

        widget.setLayout(layout)
        return widget
    
    def clear_navigation_history(self):
        """ナビゲーション履歴をクリア"""
        self.webview_navigation_log.clear()
        self.update_navigation_history()
        self.log_message("WebViewナビゲーション履歴をクリアしました")
    
    def closeEvent(self, event):
        """ウィンドウクローズ時の処理"""
        try:
            # 親コントローラーにクリーンアップを通知
            if self.parent_controller and hasattr(self.parent_controller, 'cleanup_request_analyzer_mode'):
                self.parent_controller.cleanup_request_analyzer_mode()
            
            # 実行中のスレッドを停止
            if self.current_request_thread and self.current_request_thread.isRunning():
                self.current_request_thread.terminate()
                self.current_request_thread.wait()
            
        except Exception as e:
            print(f"終了処理エラー: {e}")
        
        super().closeEvent(event)
    
    def validate_url(self, url):
        """URL検証メソッド"""
        import re
        
        try:
            # 基本的なURL形式チェック
            url_pattern = r'^https?://.+'
            if not re.match(url_pattern, url):
                return False, "有効なHTTP/HTTPSのURLを入力してください。"
            
            # RDE関連のドメインチェック
            rde_domains = [
                'rde.nims.go.jp',
                'rde-api.nims.go.jp', 
                'rde-user-api.nims.go.jp'
            ]
            
            is_rde_domain = any(domain in url for domain in rde_domains)
            
            if not is_rde_domain:
                return True, f"RDE以外のドメインです ({url})。外部APIへのアクセスに注意してください。"
            
            return True, None
            
        except Exception as e:
            return False, f"URL検証中にエラーが発生しました: {e}"
    
    def clear_request_parameters(self):
        """リクエストパラメータをクリア"""
        self.params_input.clear()
        self.form_data_input.clear()
        self.json_data_input.clear()
        
    def setup_web_get_request(self, url):
        """WEBページアクセス用のGETリクエスト設定（HTMLドキュメント取得）"""
        self.clear_request_parameters()
        self.url_input.setText(url)
        self.method_combo.setCurrentText("GET")
        
        # URLからホスト名を動的に取得
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        
        # WEBページアクセス用のヘッダー（HTMLドキュメント取得）
        web_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Host": host,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }
        
        # Bearerトークンを自動で取得・マージ
        bearer_token = self.get_bearer_token()
        if bearer_token:
            web_headers["Authorization"] = f"Bearer {bearer_token}"
        
        # ヘッダーをJSON形式で設定
        import json
        self.headers_input.setPlainText(json.dumps(web_headers, indent=2))
        
    def setup_group_detail_request(self):
        """グループ詳細取得リクエストの設定（デフォルトでARIMのサブグループを設定）"""
        # デフォルトでマテリアル先端リサーチインフラ事業のサブグループAPIを設定
        default_group_id = "4bbf62be-f270-4a46-9682-38cd064607ba"
        url = f"https://rde-api.nims.go.jp/groups/{default_group_id}?include=children%2Cmembers"
        
        self.clear_request_parameters()
        self.url_input.setText(url)
        self.method_combo.setCurrentText("GET")
        
        # URLからホスト名を動的に取得
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        
        # グループ詳細API用のヘッダー
        api_headers = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Host": host,
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        }
        
        # Bearerトークンを自動で取得・マージ
        bearer_token = self.get_bearer_token()
        if bearer_token:
            api_headers["Authorization"] = f"Bearer {bearer_token}"
        
        # ヘッダーをJSON形式で設定
        import json
        self.headers_input.setPlainText(json.dumps(api_headers, indent=2))
        
    def setup_simple_get_request(self, url):
        """シンプルなGETリクエストの設定（パラメータクリア & 適切なヘッダー設定 & Bearerトークン自動マージ）"""
        self.clear_request_parameters()
        self.url_input.setText(url)
        self.method_combo.setCurrentText("GET")
        
        # URLからホスト名を動的に取得
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        
        # ブラウザと同じヘッダーを設定（成功時のものを正確に再現）
        default_headers = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Host": host,
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\""
        }
        
        # Bearerトークンを自動取得してマージ
        token = self.get_bearer_token()
        if token:
            default_headers["Authorization"] = f"Bearer {token}"
        
        self.headers_input.setText(json.dumps(default_headers, indent=2, ensure_ascii=False))
    
    def get_bearer_token(self):
        """
        Bearer Token統一管理システムから取得
        """
        try:
            return BearerTokenManager.get_token_with_relogin_prompt(self)
        except Exception as e:
            self.log_message(f"Bearer Token取得エラー: {e}")
            return None
    
    def merge_bearer_token_to_headers(self):
        """現在のヘッダーにBearerトークンをマージ"""
        try:
            token = self.get_bearer_token()
            if not token:
                QMessageBox.warning(self, "警告", "Bearerトークンが見つかりません。\nメインのRDEツールでログインしてください。")
                return False
            
            # 現在のヘッダーを取得
            headers_text = self.headers_input.toPlainText()
            if headers_text.strip():
                try:
                    headers = json.loads(headers_text)
                except json.JSONDecodeError:
                    headers = {}
            else:
                headers = {}
            
            # Authorizationヘッダーを追加/更新
            headers["Authorization"] = f"Bearer {token}"
            
            # ヘッダーを再設定
            self.headers_input.setText(json.dumps(headers, indent=2, ensure_ascii=False))
            return True
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"Bearerトークンマージ中にエラーが発生しました: {e}")
            return False
    
    def setup_create_subgroup_request(self):
        """サブグループ作成リクエストの設定"""
        # 基本設定
        self.clear_request_parameters()
        self.url_input.setText("https://rde-api.nims.go.jp/groups")
        self.method_combo.setCurrentText("POST")
        
        # サブグループ作成用のヘッダー設定
        api_headers = {
            "Accept": "application/vnd.api+json",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Content-Type": "application/vnd.api+json",
            "Host": "rde-api.nims.go.jp",
            "Origin": "https://rde.nims.go.jp",
            "Referer": "https://rde.nims.go.jp/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "sec-ch-ua": "\"Not)A;Brand\";v=\"8\", \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\""
        }
        
        # Bearerトークンを取得
        bearer_token = self.get_bearer_token()
        if bearer_token:
            api_headers["Authorization"] = f"Bearer {bearer_token}"
        
        # ヘッダーをJSON形式で設定
        self.headers_input.setPlainText(json.dumps(api_headers, indent=2, ensure_ascii=False))
        
        # サンプルペイロード（実際の値は手動で変更）
        sample_payload = {
            "data": {
                "type": "group",
                "attributes": {
                    "name": "サンプル-テストグループ",
                    "description": "サンプル-テストグループの説明",
                    "subjects": [],
                    "funds": [],
                    "roles": [{
                        "userId": "03b8fc123d0a67ba407dd2f06fe49768d9cbddca6438366632366466",
                        "role": "OWNER",
                        "canCreateDatasets": False,
                        "canEditMembers": False
                    }]
                },
                "relationships": {
                    "parent": {
                        "data": {
                            "type": "group",
                            "id": "1af3d7dd-bea8-4508-84dc-6990cd8c6753"  # 東北大学のグループID
                        }
                    }
                }
            }
        }
        
        # ペイロードを設定
        self.json_data_input.setPlainText(json.dumps(sample_payload, indent=2, ensure_ascii=False))
        
        # 情報表示
        QMessageBox.information(
            self, 
            "サブグループ作成設定完了", 
            "サブグループ作成用のリクエストが設定されました。\n\n"
            "ペイロードの以下の項目を必要に応じて変更してください：\n"
            "• name: グループ名\n"
            "• description: グループ説明\n"
            "• userId: 所有者のユーザーID\n"
            "• parent.id: 親グループのID（現在は東北大学）\n\n"
            "設定後、「送信」ボタンでリクエストを実行してください。"
        )

def main():
    """メイン実行（パスワード認証付き）"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # モダンなUIスタイル
    
    # パスワード認証ダイアログを表示
    auth_dialog = PasswordAuthDialog()
    auth_dialog.load_password_config()  # 設定ファイルからパスワード読み込み
    
    if auth_dialog.exec() == QDialog.Accepted:
        # 認証成功時のみメインウィンドウを表示
        window = RDEDatasetCreationGUI()
        window.show()
        
        sys.exit(app.exec())
    else:
        # 認証失敗またはキャンセル時は終了
        sys.exit(0)


def create_authenticated_gui(parent_webview=None, parent_controller=None):
    """認証付きGUI作成関数（外部からの呼び出し用）"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setStyle('Fusion')
    
    # パスワード認証ダイアログを表示
    auth_dialog = PasswordAuthDialog()
    auth_dialog.load_password_config()
    
    if auth_dialog.exec() == QDialog.Accepted:
        # 認証成功時のみメインウィンドウを作成・表示
        window = RDEDatasetCreationGUI(parent_webview, parent_controller)
        window.show()
        return window
    else:
        # 認証失敗またはキャンセル時はNoneを返す
        return None


if __name__ == "__main__":
    main()
