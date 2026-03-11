"""
ログイン設定タブ UI

データポータルサイトへのログイン認証情報を管理するタブ
"""

import os
from datetime import datetime
from pathlib import Path

from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QLabel, QLineEdit, QPushButton, QComboBox,
    QFormLayout, QTextEdit, QMessageBox
)
from qt_compat.core import Qt, Signal, QTimer, QThread

from classes.theme import get_color, ThemeKey
from classes.theme.theme_manager import ThemeManager
from classes.utils.button_styles import get_button_style

from classes.managers.log_manager import get_logger
from ..core.auth_manager import get_auth_manager, PortalCredentials, AuthManager
from ..conf.config import get_data_portal_config
from ..util.managed_csv_paths import build_managed_csv_path, find_latest_managed_csv, format_mtime_jst, format_size

logger = get_logger("DataPortal.LoginSettingsTab")


class _DownloadManagedCsvThread(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, *, environment: str, client, parent=None):
        super().__init__(parent)
        self.environment = str(environment or "").strip() or "production"
        self.client = client

    def run(self) -> None:  # noqa: D401
        try:
            ok, resp = self.client.download_theme_csv()
            if not ok:
                self.failed.emit(str(resp))
                return

            payload = getattr(resp, "content", None)
            if isinstance(payload, bytes):
                data = payload
            else:
                text = getattr(resp, "text", "")
                data = (text or "").encode("utf-8", errors="replace")

            if not data:
                self.failed.emit("CSVの内容が空です")
                return

            path = build_managed_csv_path(self.environment, now=datetime.now())
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            path.write_bytes(data)
            self.succeeded.emit(str(path))
        except Exception as exc:
            self.failed.emit(str(exc))


class _AutoConnectionTestThread(QThread):
    progress = Signal(str, bool, str)

    def __init__(self, targets: list[tuple[str, PortalCredentials]], parent=None):
        super().__init__(parent)
        self._targets = list(targets or [])
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:  # noqa: D401
        from ..core.portal_client import PortalClient

        for env, credentials in self._targets:
            if self._stop_requested:
                break
            try:
                client = PortalClient(str(env or "").strip() or "production")
                client.set_credentials(credentials)
                success, message = client.test_connection()
                self.progress.emit(str(env), bool(success), str(message or ""))
            except Exception as exc:
                self.progress.emit(str(env), False, str(exc))


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
        self.setObjectName("dataPortalLoginSettingsTab")
        
        self.auth_manager = get_auth_manager()
        self.portal_client = None

        # Debounce/guard for auto-tests
        self._auto_test_inflight = False
        self._auto_test_done = False
        self._auto_test_thread: _AutoConnectionTestThread | None = None
        
        self._init_ui()
        self._load_available_environments()
        logger.info("ログイン設定タブ初期化完了")

    def _build_base_stylesheet(self) -> str:
        return f"""
            QWidget#dataPortalLoginSettingsTab QLabel#dataPortalUrlLabel,
            QWidget#dataPortalLoginSettingsTab QLabel#dataPortalManagedCsvInfoLabel {{
                color: {get_color(ThemeKey.TEXT_MUTED)};
                font-size: 10px;
            }}
            QWidget#dataPortalLoginSettingsTab QLabel[dataRole="sectionLabel"] {{
                font-weight: bold;
            }}
            QWidget#dataPortalLoginSettingsTab QPushButton#dataPortalSaveButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QWidget#dataPortalLoginSettingsTab QPushButton#dataPortalSaveButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QWidget#dataPortalLoginSettingsTab QPushButton#dataPortalLoadButton,
            QWidget#dataPortalLoginSettingsTab QPushButton#dataPortalFetchCsvButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QWidget#dataPortalLoginSettingsTab QPushButton#dataPortalLoadButton:hover,
            QWidget#dataPortalLoginSettingsTab QPushButton#dataPortalFetchCsvButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
            QWidget#dataPortalLoginSettingsTab QPushButton#dataPortalTestButton {{
                background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QWidget#dataPortalLoginSettingsTab QPushButton#dataPortalTestButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)};
            }}
            QWidget#dataPortalLoginSettingsTab QPushButton#dataPortalClearButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QWidget#dataPortalLoginSettingsTab QPushButton#dataPortalClearButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
            }}
            QWidget#dataPortalLoginSettingsTab QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            }}
        """

    def showEvent(self, event):
        """表示時に自動接続テストを一度だけ走らせる。"""
        try:
            super().showEvent(event)
        except Exception:
            # super が無い/失敗しても自動テストは可能な限り実行
            pass

        # 初回表示時にだけ実行（タブ描画完了後に遅延開始）
        try:
            QTimer.singleShot(200, self.auto_test_connections)
        except Exception:
            pass
    
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

        # 管理CSV（最新版）情報
        self.managed_csv_info_label = QLabel("")
        self.managed_csv_info_label.setObjectName("dataPortalManagedCsvInfoLabel")
        self.managed_csv_info_label.setWordWrap(True)
        layout.addWidget(self.managed_csv_info_label)
        
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

        # テーマ変更イベントに追従（個別 styleSheet の色埋め込み更新）
        try:
            self._theme_manager = ThemeManager.instance()
            self._theme_slot = self.refresh_theme
            self._theme_manager.theme_changed.connect(self._theme_slot)

            def _disconnect_theme_slot(*_args):
                try:
                    self._theme_manager.theme_changed.disconnect(self._theme_slot)
                except Exception:
                    pass

            try:
                self.destroyed.connect(_disconnect_theme_slot)
            except Exception:
                pass
        except Exception:
            pass
    
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
        self.setStyleSheet(self._build_base_stylesheet())
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
        self.url_label.setObjectName("dataPortalUrlLabel")
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
        basic_label.setProperty("dataRole", "sectionLabel")
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
        login_label.setProperty("dataRole", "sectionLabel")
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
        self.save_btn.setObjectName("dataPortalSaveButton")
        self.save_btn.clicked.connect(self._on_save_credentials)
        layout.addWidget(self.save_btn)
        
        # 読込ボタン
        self.load_btn = QPushButton("📂 認証情報を読込")
        self.load_btn.setObjectName("dataPortalLoadButton")
        self.load_btn.clicked.connect(self._on_load_credentials)
        layout.addWidget(self.load_btn)
        
        # クリアボタン
        self.clear_btn = QPushButton("🗑️ クリア")
        self.clear_btn.setObjectName("dataPortalClearButton")
        self.clear_btn.clicked.connect(self._on_clear_form)
        layout.addWidget(self.clear_btn)
        
        layout.addStretch()
        
        # テストログインボタン
        self.test_login_btn = QPushButton("🔌 接続テスト")
        self.test_login_btn.setObjectName("dataPortalTestButton")
        self.test_login_btn.clicked.connect(self._on_test_login)
        layout.addWidget(self.test_login_btn)

        # 管理CSV取得ボタン
        self.fetch_csv_btn = QPushButton("⬇️ CSV取得")
        self.fetch_csv_btn.setObjectName("dataPortalFetchCsvButton")
        self.fetch_csv_btn.clicked.connect(self._on_fetch_managed_csv)
        layout.addWidget(self.fetch_csv_btn)
        
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

            self._refresh_managed_csv_info()
        else:
            self.url_label.setText("設定なし")
            self._log_status(f"⚠️ 環境 '{environment}' の設定が見つかりません", error=True)

            self._refresh_managed_csv_info()

    def _refresh_managed_csv_info(self) -> None:
        env = str(self.env_combo.currentData() or "production")
        try:
            info = find_latest_managed_csv(env)
        except Exception:
            info = None

        if info is None:
            self.managed_csv_info_label.setText(f"管理CSV(最新): なし（{env}）")
            return

        ts = format_mtime_jst(info.mtime)
        sz = format_size(info.size_bytes)
        name = info.path.name
        self.managed_csv_info_label.setText(f"管理CSV(最新): {ts} / {sz} / {name}（{env}）")
    
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

        credentials, err = self._credentials_from_form()
        if credentials is None:
            self._show_error(err or "ログイン情報を入力してください")
            return

        self._run_connection_test(environment, credentials, interactive=True)

    def _on_fetch_managed_csv(self) -> None:
        """管理CSV（テーマ一覧CSV）を取得して保存する。"""

        env = str(self.env_combo.currentData() or "").strip()
        if not env:
            self._show_error("環境が選択されていません")
            return

        client = self.create_portal_client_for_environment(env)
        if client is None:
            self._show_error("認証情報が不足しています（保存済み認証情報、またはフォーム入力を確認してください）")
            return

        # pytestでは同期実行（widgetテスト安定化 + ネットワークはダミークライアントで回避）
        if os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                ok, resp = client.download_theme_csv()
                if not ok:
                    self._log_status(f"❌ 管理CSV取得失敗({env}): {resp}", error=True)
                    return

                payload = getattr(resp, "content", None)
                if isinstance(payload, bytes):
                    data = payload
                else:
                    data = (getattr(resp, "text", "") or "").encode("utf-8", errors="replace")

                path = build_managed_csv_path(env, now=datetime.now())
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                path.write_bytes(data)
                self._log_status(f"✅ 管理CSV保存: {path}")
                self._refresh_managed_csv_info()
            except Exception as exc:
                self._log_status(f"❌ 管理CSV取得エラー({env}): {exc}", error=True)
            return

        self.fetch_csv_btn.setEnabled(False)
        self.fetch_csv_btn.setText("取得中...")
        self._log_status(f"⬇️ 管理CSV取得開始: {env}")

        self._csv_thread = _DownloadManagedCsvThread(environment=env, client=client, parent=self)
        self._csv_thread.succeeded.connect(self._on_fetch_managed_csv_succeeded)
        self._csv_thread.failed.connect(self._on_fetch_managed_csv_failed)
        self._csv_thread.finished.connect(lambda: self.fetch_csv_btn.setEnabled(True))
        self._csv_thread.finished.connect(lambda: self.fetch_csv_btn.setText("⬇️ CSV取得"))
        self._csv_thread.start()

    def _on_fetch_managed_csv_succeeded(self, path: str) -> None:
        self._log_status(f"✅ 管理CSV保存: {path}")
        self._refresh_managed_csv_info()

    def _on_fetch_managed_csv_failed(self, message: str) -> None:
        env = str(self.env_combo.currentData() or "production")
        self._log_status(f"❌ 管理CSV取得失敗({env}): {message}", error=True)
        self._show_error(f"管理CSV取得に失敗しました\n{message}")

    def _credentials_from_form(self) -> tuple[PortalCredentials | None, str | None]:
        """フォーム入力からPortalCredentialsを構築する（不足時はエラーを返す）"""

        basic_user = self.basic_user_input.text().strip()
        basic_pass = self.basic_pass_input.text().strip()
        login_user = self.login_user_input.text().strip()
        login_pass = self.login_pass_input.text().strip()

        if not login_user or not login_pass:
            return None, "ログイン情報を入力してください"

        credentials = PortalCredentials(
            basic_username=basic_user or "",
            basic_password=basic_pass or "",
            login_username=login_user,
            login_password=login_pass,
        )
        return credentials, None

    def create_portal_client_for_environment(self, environment: str):
        """保存済み/フォーム入力から PortalClient を作成して返す。

        - 接続テストは行わない（各機能側で必要なAPIを叩くときに失敗するなら失敗させる）
        - 既存の「接続テスト必須」導線を解消するためのヘルパ
        """

        env = str(environment or "").strip()
        if not env:
            return None

        credentials = None
        try:
            if self.auth_manager.has_credentials(env):
                credentials = self.auth_manager.get_credentials(env)
        except Exception:
            credentials = None

        if credentials is None:
            # フォームが同一環境の場合だけフォーム入力を使う
            try:
                if self.env_combo.currentData() == env:
                    credentials, _err = self._credentials_from_form()
            except Exception:
                credentials = None

        if credentials is None:
            return None

        try:
            from ..core.portal_client import PortalClient

            client = PortalClient(env)
            client.set_credentials(credentials)
            return client
        except Exception:
            return None

    def auto_test_connections(self) -> None:
        """ログイン設定タブ表示時の自動接続テスト（本番/テスト）。

        - UIブロック/ポップアップは出さず、ステータス欄へ結果を出す。
        - pytest実行中はネットワークを避けるためスキップする。
        """

        if self._auto_test_done:
            return
        if os.environ.get("PYTEST_CURRENT_TEST"):
            self._log_status("(pytest) 自動接続テストはスキップしました")
            self._auto_test_done = True
            return
        if self._auto_test_inflight:
            return
        # 設定されている環境のみを対象にする（本番→テストの順）
        config = get_data_portal_config()
        available = list(config.get_available_environments())
        target_envs = [env for env in ["production", "test"] if env in available]

        targets: list[tuple[str, PortalCredentials]] = []
        for env in target_envs:
            if not self.auth_manager.has_credentials(env):
                self._log_status(f"⚠️ 自動接続テスト: {env} は認証情報未登録")
                continue
            creds = self.auth_manager.get_credentials(env)
            if not creds:
                self._log_status(f"⚠️ 自動接続テスト: {env} の認証情報読込に失敗")
                continue
            targets.append((env, creds))

        if not targets:
            self._auto_test_done = True
            return

        self._auto_test_inflight = True
        self._log_status("🔌 自動接続テストをバックグラウンド実行します")

        thread = _AutoConnectionTestThread(targets, parent=self)
        thread.progress.connect(self._on_auto_test_progress)
        thread.finished.connect(self._on_auto_test_finished)
        self._auto_test_thread = thread
        thread.start()

    def _on_auto_test_progress(self, environment: str, success: bool, message: str) -> None:
        env = str(environment or "").strip() or "production"
        if success:
            try:
                if self.env_combo.currentData() == env:
                    self.portal_client = self.create_portal_client_for_environment(env)
            except Exception:
                pass
            self._log_status(f"✅ 接続テスト成功({env}): {message}")
        else:
            self._log_status(f"❌ 接続テスト失敗({env}): {message}", error=True)

    def _on_auto_test_finished(self) -> None:
        self._auto_test_inflight = False
        self._auto_test_done = True
        if self._auto_test_thread is not None:
            try:
                self._auto_test_thread.deleteLater()
            except Exception:
                pass
        self._auto_test_thread = None

    def _run_connection_test(self, environment: str, credentials: PortalCredentials, *, interactive: bool) -> None:
        """接続テスト実行（interactive=Falseの場合はポップアップなし）。"""

        env = str(environment or "").strip()
        if not env:
            return

        self._log_status(f"🔌 接続テスト開始: {env}")
        if interactive:
            self.test_login_btn.setEnabled(False)
            self.test_login_btn.setText("テスト中...")

        try:
            from ..core.portal_client import PortalClient

            client = PortalClient(env)
            client.set_credentials(credentials)
            success, message = client.test_connection()

            if success:
                # 成功時は、現在選択中の環境なら portal_client を保持する（既存挙動維持）
                try:
                    if self.env_combo.currentData() == env:
                        self.portal_client = client
                except Exception:
                    pass
                self._log_status(f"✅ 接続テスト成功({env}): {message}")
                if interactive:
                    self._show_info(f"接続テスト成功\n{message}")
                    self.login_test_completed.emit(True, message)
            else:
                if interactive:
                    self.portal_client = None
                self._log_status(f"❌ 接続テスト失敗({env}): {message}", error=True)
                if interactive:
                    self._show_error(f"接続テスト失敗\n{message}")
                    self.login_test_completed.emit(False, message)
        except Exception as e:
            if interactive:
                self.portal_client = None
            error_msg = f"接続テストエラー({env}): {e}"
            self._log_status(f"❌ {error_msg}", error=True)
            if interactive:
                self._show_error(error_msg)
                self.login_test_completed.emit(False, str(e))
        finally:
            if interactive:
                self.test_login_btn.setEnabled(True)
                self.test_login_btn.setText("🔌 接続テスト")
    
    def _log_status(self, message: str, error: bool = False):
        """ステータスログ出力"""
        # 仕様: 文字列ごとに配色は指定しない（テーマ側の QTextEdit QSS に委ねる）
        # error は文頭アイコン(❌/⚠️ 等)で区別し、色は固定しない。
        self.status_text.append(message)
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
