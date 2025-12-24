"""
ログイン設定タブ UI

データポータルサイトへのログイン認証情報を管理するタブ
"""

from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QLabel, QLineEdit, QPushButton, QComboBox,
    QFormLayout, QTextEdit, QMessageBox
)
from qt_compat.core import Qt, Signal

from classes.theme import get_color, ThemeKey

from classes.managers.log_manager import get_logger
from ..core.auth_manager import get_auth_manager, PortalCredentials, AuthManager
from ..core.portal_client import PortalClient
from ..conf.config import get_data_portal_config

logger = get_logger("DataPortal.LoginSettingsTab")


class LoginSettingsTab(QWidget):
    """
    ログイン設定タブ
    
    機能:
    - 環境選択（テスト/本番）
    - 認証情報入力フォーム
    - 認証情報の保存/読込
    - テストログイン
    """
    
    # シグナル定義
    credentials_saved = Signal(str)  # 環境名
    login_test_completed = Signal(bool, str)  # 成功フラグ, メッセージ
    
    def __init__(self, parent=None):
        """初期化"""
        super().__init__(parent)
        
        self.auth_manager = get_auth_manager()
        self.portal_client = None
        
        self._init_ui()
        self._load_available_environments()
        logger.info("ログイン設定タブ初期化完了")
    
    def _init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 環境選択セクション
        env_group = self._create_environment_selector()
        layout.addWidget(env_group)
        
        # 認証情報入力セクション
        auth_group = self._create_auth_form()
        layout.addWidget(auth_group)
        
        # ボタンセクション
        button_layout = self._create_button_section()
        layout.addLayout(button_layout)
        
        # ステータス表示エリア
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(150)
        self.status_text.setPlaceholderText("操作ログがここに表示されます...")
        self.status_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        layout.addWidget(QLabel("ステータス:"))
        layout.addWidget(self.status_text)
        
        layout.addStretch()
    
    def _apply_status_style(self):
        """ステータステキストスタイルを適用"""
        self.status_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
    
    def refresh_theme(self):
        """テーマ変更時のスタイル更新"""
        self._apply_status_style()
        self.update()
    
    def _create_environment_selector(self) -> QGroupBox:
        """環境選択セクション作成"""
        group = QGroupBox("環境選択")
        layout = QFormLayout()
        
        # 環境選択コンボボックス
        self.env_combo = QComboBox()
        self.env_combo.currentTextChanged.connect(self._on_environment_changed)
        layout.addRow("環境:", self.env_combo)
        
        # URL表示（読み取り専用）
        self.url_label = QLabel("")
        self.url_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px;")
        self.url_label.setWordWrap(True)
        layout.addRow("URL:", self.url_label)
        
        group.setLayout(layout)
        return group
    
    def _create_auth_form(self) -> QGroupBox:
        """認証情報入力フォーム作成"""
        group = QGroupBox("認証情報")
        layout = QFormLayout()
        
        # Basic認証情報
        basic_label = QLabel("Basic認証")
        basic_label.setStyleSheet("font-weight: bold;")
        layout.addRow(basic_label)
        
        self.basic_user_input = QLineEdit()
        self.basic_user_input.setPlaceholderText("Basic認証ユーザー名")
        layout.addRow("ユーザー名:", self.basic_user_input)
        
        self.basic_pass_input = QLineEdit()
        self.basic_pass_input.setEchoMode(QLineEdit.Password)
        self.basic_pass_input.setPlaceholderText("Basic認証パスワード")
        layout.addRow("パスワード:", self.basic_pass_input)
        
        # スペーサー
        layout.addRow(QLabel(""))
        
        # ログイン情報
        login_label = QLabel("ログイン情報")
        login_label.setStyleSheet("font-weight: bold;")
        layout.addRow(login_label)
        
        self.login_user_input = QLineEdit()
        self.login_user_input.setPlaceholderText("ログインユーザー名（メールアドレス等）")
        layout.addRow("ユーザー名:", self.login_user_input)
        
        self.login_pass_input = QLineEdit()
        self.login_pass_input.setEchoMode(QLineEdit.Password)
        self.login_pass_input.setPlaceholderText("ログインパスワード")
        layout.addRow("パスワード:", self.login_pass_input)
        
        group.setLayout(layout)
        return group
    
    def _create_button_section(self) -> QHBoxLayout:
        """ボタンセクション作成"""
        layout = QHBoxLayout()
        
        # 保存ボタン
        self.save_btn = QPushButton("💾 認証情報を保存")
        self.save_btn.clicked.connect(self._on_save_credentials)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)
        layout.addWidget(self.save_btn)
        
        # 読込ボタン
        self.load_btn = QPushButton("📂 認証情報を読込")
        self.load_btn.clicked.connect(self._on_load_credentials)
        self.load_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
        """)
        layout.addWidget(self.load_btn)
        
        # クリアボタン
        self.clear_btn = QPushButton("🗑️ クリア")
        self.clear_btn.clicked.connect(self._on_clear_form)
        layout.addWidget(self.clear_btn)
        
        layout.addStretch()
        
        # テストログインボタン
        self.test_login_btn = QPushButton("🔌 接続テスト")
        self.test_login_btn.clicked.connect(self._on_test_login)
        self.test_login_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)};
            }}
        """)
        layout.addWidget(self.test_login_btn)
        
        return layout
    
    def _load_available_environments(self):
        """利用可能な環境をコンボボックスに読み込む"""
        config = get_data_portal_config()
        environments = config.get_available_environments()
        
        self.env_combo.clear()
        for env in environments:
            # 表示名を統一（テスト環境 or 本番環境のみ）
            if env == "production":
                display_name = "本番環境"
            elif env == "test":
                display_name = "テスト環境"
            else:
                # test, production以外は表示しない（既にフィルタ済みだが念のため）
                continue
            self.env_combo.addItem(display_name, env)
        
        if environments:
            self._on_environment_changed(self.env_combo.currentText())
    
    def _on_environment_changed(self, display_name: str):
        """環境選択変更時の処理"""
        environment = self.env_combo.currentData()
        if not environment:
            return
        
        config = get_data_portal_config()
        env_config = config.get_environment_config(environment)
        
        if env_config:
            self.url_label.setText(env_config.url)
            self._log_status(f"環境切替: {display_name} ({environment})")
            
            # 保存済み認証情報があれば自動読込
            if self.auth_manager.has_credentials(environment):
                self._auto_load_credentials(environment)
        else:
            self.url_label.setText("設定なし")
            self._log_status(f"⚠️ 環境 '{environment}' の設定が見つかりません", error=True)
    
    def _on_save_credentials(self):
        """認証情報保存"""
        environment = self.env_combo.currentData()
        if not environment:
            self._show_error("環境が選択されていません")
            return
        
        # 入力値取得
        basic_user = self.basic_user_input.text().strip()
        basic_pass = self.basic_pass_input.text().strip()
        login_user = self.login_user_input.text().strip()
        login_pass = self.login_pass_input.text().strip()
        
        # 必須チェック（Basic認証はオプション）
        if not login_user or not login_pass:
            self._show_error("ログイン情報（ユーザー名・パスワード）は必須です")
            return
        
        # 認証情報オブジェクト作成
        credentials = PortalCredentials(
            basic_username=basic_user or "",
            basic_password=basic_pass or "",
            login_username=login_user,
            login_password=login_pass
        )
        
        # 保存実行
        if self.auth_manager.store_credentials(environment, credentials):
            self._log_status(f"✅ 認証情報を保存しました: {environment}")
            self.credentials_saved.emit(environment)
            self._show_info("認証情報を保存しました")
        else:
            self._log_status(f"❌ 認証情報の保存に失敗しました", error=True)
            self._show_error("認証情報の保存に失敗しました")
    
    def _auto_load_credentials(self, environment: str):
        """認証情報を自動読込（環境変更時）"""
        credentials = self.auth_manager.get_credentials(environment)
        
        if credentials:
            self.basic_user_input.setText(credentials.basic_username)
            self.basic_pass_input.setText(credentials.basic_password)
            self.login_user_input.setText(credentials.login_username)
            self.login_pass_input.setText(credentials.login_password)
            
            self._log_status(f"✅ 保存済み認証情報を自動読込しました: {environment}")
        else:
            # 認証情報がない場合はフォームをクリア
            self.basic_user_input.clear()
            self.basic_pass_input.clear()
            self.login_user_input.clear()
            self.login_pass_input.clear()
            self._log_status(f"💡 {environment} の認証情報が未登録です")
    
    def _on_load_credentials(self):
        """認証情報読込（手動）"""
        environment = self.env_combo.currentData()
        if not environment:
            self._show_error("環境が選択されていません")
            return
        
        credentials = self.auth_manager.get_credentials(environment)
        
        if credentials:
            self.basic_user_input.setText(credentials.basic_username)
            self.basic_pass_input.setText(credentials.basic_password)
            self.login_user_input.setText(credentials.login_username)
            self.login_pass_input.setText(credentials.login_password)
            
            self._log_status(f"✅ 認証情報を読み込みました: {environment}")
            self._show_info("認証情報を読み込みました")
        else:
            self._log_status(f"⚠️ 保存された認証情報が見つかりません: {environment}", error=True)
            self._show_warning("保存された認証情報が見つかりません")
    
    def _on_clear_form(self):
        """フォームクリア"""
        self.basic_user_input.clear()
        self.basic_pass_input.clear()
        self.login_user_input.clear()
        self.login_pass_input.clear()
        self._log_status("フォームをクリアしました")
    
    def _on_test_login(self):
        """テストログイン実行"""
        environment = self.env_combo.currentData()
        if not environment:
            self._show_error("環境が選択されていません")
            return
        
        # 入力値取得
        basic_user = self.basic_user_input.text().strip()
        basic_pass = self.basic_pass_input.text().strip()
        login_user = self.login_user_input.text().strip()
        login_pass = self.login_pass_input.text().strip()
        
        if not login_user or not login_pass:
            self._show_error("ログイン情報を入力してください")
            return
        
        credentials = PortalCredentials(
            basic_username=basic_user or "",
            basic_password=basic_pass or "",
            login_username=login_user,
            login_password=login_pass
        )
        
        self._log_status(f"🔌 接続テスト開始: {environment}")
        self.test_login_btn.setEnabled(False)
        self.test_login_btn.setText("テスト中...")
        
        try:
            # PortalClient作成
            client = PortalClient(environment)
            client.set_credentials(credentials)
            
            # 接続テスト
            success, message = client.test_connection()
            
            if success:
                # 成功時にクライアントを保持
                self.portal_client = client
                self._log_status(f"✅ 接続テスト成功: {message}")
                self._show_info(f"接続テスト成功\n{message}")
                self.login_test_completed.emit(True, message)
            else:
                self.portal_client = None
                self._log_status(f"❌ 接続テスト失敗: {message}", error=True)
                self._show_error(f"接続テスト失敗\n{message}")
                self.login_test_completed.emit(False, message)
                
        except Exception as e:
            self.portal_client = None
            error_msg = f"接続テストエラー: {e}"
            self._log_status(f"❌ {error_msg}", error=True)
            self._show_error(error_msg)
            self.login_test_completed.emit(False, str(e))
        finally:
            self.test_login_btn.setEnabled(True)
            self.test_login_btn.setText("🔌 接続テスト")
    
    def _log_status(self, message: str, error: bool = False):
        """ステータスログ出力"""
        if error:
            style = f"color: {get_color(ThemeKey.TEXT_ERROR)};"
        else:
            style = f"color: {get_color(ThemeKey.INPUT_TEXT)};"
        
        self.status_text.append(f'<span style="{style}">{message}</span>')
        logger.info(message)
    
    def _show_info(self, message: str):
        """情報メッセージ表示"""
        QMessageBox.information(self, "情報", message)
    
    def _show_warning(self, message: str):
        """警告メッセージ表示"""
        QMessageBox.warning(self, "警告", message)
    
    def _show_error(self, message: str):
        """エラーメッセージ表示"""
        QMessageBox.critical(self, "エラー", message)
