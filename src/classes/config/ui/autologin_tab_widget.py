#!/usr/bin/env python3
"""
自動ログインタブウィジェット - ARIM RDE Tool v1.16
認証情報の保存・取得・ソース選択の統合UI

主要機能:
- 認証情報の保存・削除
- 保存先の選択（OSキーチェーン/暗号化ファイル/レガシーファイル）
- ヘルスチェック結果表示
- レガシーファイル警告管理
"""

import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime

try:
    # WebEngine初期化問題の回避
    from qt_compat import initialize_webengine
    from qt_compat.core import Qt
    
    # WebEngine初期化
    initialize_webengine()
    
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QPushButton, QLineEdit, QRadioButton, QButtonGroup,
        QCheckBox, QGroupBox, QTextEdit, QMessageBox, QProgressBar,
        QFrame, QSizePolicy, QComboBox
    )
    from qt_compat.core import QTimer, QThread, Signal
    from qt_compat.gui import QFont, QPalette
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    # ダミークラス定義
    class QWidget: pass
    class QThread: pass
    def Signal(*args): pass

from classes.core.credential_store import (
    perform_health_check, decide_autologin_source, get_credential_store,
    CredentialInfo, CredentialStoreHealthCheck
)
from classes.managers.app_config_manager import get_config_manager
from classes.theme import get_color, ThemeKey

# ログ設定
logger = logging.getLogger(__name__)

class AutoLoginTabWidget(QWidget):
    """自動ログインタブウィジェット"""
    
    def __init__(self, parent=None):
        # PySide6完全対応: QWidget.__init__を明示的に呼び出し
        QWidget.__init__(self, parent)
            
        if not PYQT5_AVAILABLE:
            logger.warning("PyQt5が利用できないため、自動ログインタブを初期化できません")
            return
        
        self.parent_widget = parent
        self.config_manager = get_config_manager()
        self.health_check_result: Optional[CredentialStoreHealthCheck] = None
        
        self.init_ui()
        self.load_current_settings()
        self.perform_health_check()
    
    def init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # タイトル - タブ内に表示されるため不要（コメントアウト）
        # title_label = QLabel("自動ログイン設定")
        # title_font = QFont()
        # title_font.setPointSize(14)
        # title_font.setBold(True)
        # title_label.setFont(title_font)
        # layout.addWidget(title_label)
        
        # セクションA: 状態表示
        self.setup_status_section(layout)
        
        # セクションB: 基本設定
        self.setup_basic_settings_section(layout)
        
        # セクションC: 認証情報
        self.setup_credentials_section(layout)
        
        # セクションD: レガシーファイル互換
        self.setup_legacy_section(layout)
        
        layout.addStretch()
    
    def setup_status_section(self, layout):
        """セクションA: 状態表示"""
        status_group = QGroupBox("現在の状態")
        status_layout = QVBoxLayout(status_group)
        
        # 現在の保存先表示
        self.current_source_label = QLabel("現在の保存先: 確認中...")
        status_layout.addWidget(self.current_source_label)
        
        # ヘルスチェック結果
        self.health_status_text = QTextEdit()
        self.health_status_text.setMaximumHeight(100)
        self.health_status_text.setReadOnly(True)
        status_layout.addWidget(self.health_status_text)
        
        # ヘルスチェック再実行ボタン
        health_check_btn = QPushButton("ヘルスチェック再実行")
        health_check_btn.clicked.connect(self.perform_health_check)
        status_layout.addWidget(health_check_btn)
        
        # 推奨メッセージ
        recommendation_label = QLabel("💡 OSキーチェーンが最も安全です")
        recommendation_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_INFO)}; font-style: italic;")
        status_layout.addWidget(recommendation_label)
        
        layout.addWidget(status_group)
    
    def setup_basic_settings_section(self, layout):
        """セクションB: 基本設定"""
        basic_group = QGroupBox("基本設定")
        basic_layout = QVBoxLayout(basic_group)
        
        # 自動ログイン有効化チェックボックス
        self.autologin_enabled_checkbox = QCheckBox("自動ログインを有効にする")
        self.autologin_enabled_checkbox.setStyleSheet("font-weight: bold; font-size: 11pt;")
        basic_layout.addWidget(self.autologin_enabled_checkbox)
        
        # 保存先選択
        storage_frame = QFrame()
        storage_layout = QGridLayout(storage_frame)
        
        storage_layout.addWidget(QLabel("保存先:"), 0, 0)
        
        # ラジオボタングループ
        self.storage_group = QButtonGroup()
        
        self.auto_radio = QRadioButton("自動（推奨）")
        self.auto_radio.setToolTip("利用可能な最も安全な保存先を自動選択")
        self.storage_group.addButton(self.auto_radio, 0)
        storage_layout.addWidget(self.auto_radio, 0, 1)
        
        self.os_keychain_radio = QRadioButton("OSキーチェーン")
        self.os_keychain_radio.setToolTip("Windows Credential Manager / macOS Keychain / Linux Secret Service")
        self.storage_group.addButton(self.os_keychain_radio, 1)
        storage_layout.addWidget(self.os_keychain_radio, 1, 1)
        
        self.encrypted_file_radio = QRadioButton("暗号化ファイル（マシン限定）")
        self.encrypted_file_radio.setToolTip("AES-GCM暗号化、DPAPI/キーチェーンで鍵保護")
        self.storage_group.addButton(self.encrypted_file_radio, 2)
        storage_layout.addWidget(self.encrypted_file_radio, 2, 1)
        
        self.legacy_file_radio = QRadioButton("旧 login.txt（非推奨）")
        self.legacy_file_radio.setToolTip("平文保存のため非推奨")
        self.legacy_file_radio.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_WARNING)};")
        self.storage_group.addButton(self.legacy_file_radio, 3)
        storage_layout.addWidget(self.legacy_file_radio, 3, 1)
        
        self.none_radio = QRadioButton("保存しない")
        self.none_radio.setToolTip("都度手動入力")
        self.storage_group.addButton(self.none_radio, 4)
        storage_layout.addWidget(self.none_radio, 4, 1)
        
        basic_layout.addWidget(storage_frame)
        
        # 設定保存ボタンを追加
        settings_button_layout = QHBoxLayout()
        settings_button_layout.addStretch()
        
        self.save_settings_button = QPushButton("💾 設定を保存")
        self.save_settings_button.clicked.connect(self.save_current_settings)
        self.save_settings_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                font-weight: bold;
                padding: 8px 20px;
                border-radius: 4px;
                font-size: 11pt;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
        """)
        self.save_settings_button.setToolTip("自動ログイン有効化と保存先設定を保存します")
        settings_button_layout.addWidget(self.save_settings_button)
        
        basic_layout.addLayout(settings_button_layout)
        
        layout.addWidget(basic_group)
    
    def setup_credentials_section(self, layout):
        """セクションC: 認証情報"""
        creds_group = QGroupBox("認証情報")
        creds_layout = QGridLayout(creds_group)
        
        # ユーザーID
        creds_layout.addWidget(QLabel("ユーザーID:"), 0, 0)
        self.username_edit = QLineEdit()
        creds_layout.addWidget(self.username_edit, 0, 1)
        
        # パスワード
        creds_layout.addWidget(QLabel("パスワード:"), 1, 0)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        creds_layout.addWidget(self.password_edit, 1, 1)
        
        # ログインモード
        creds_layout.addWidget(QLabel("ログインモード:"), 2, 0)
        self.login_mode_combo = QComboBox()
        self.login_mode_combo.addItem("dice", "dice")  # 表示名, 値
        self.login_mode_combo.setToolTip("現在はDICE認証のみ対応")
        creds_layout.addWidget(self.login_mode_combo, 2, 1)
        
        # ボタン行
        button_layout = QHBoxLayout()
        
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self.save_credentials)
        button_layout.addWidget(self.save_button)
        
        self.load_button = QPushButton("読み込み")
        self.load_button.clicked.connect(self.load_credentials)
        button_layout.addWidget(self.load_button)
        
        self.delete_button = QPushButton("削除")
        self.delete_button.clicked.connect(self.delete_credentials)
        button_layout.addWidget(self.delete_button)
        
        # RDEページを開くボタン
        self.open_rde_button = QPushButton("RDEページを開く")
        self.open_rde_button.clicked.connect(self.open_rde_page)
        self.open_rde_button.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_INFO)};")
        #button_layout.addWidget(self.open_rde_button)
        
        creds_layout.addLayout(button_layout, 3, 0, 1, 2)
        
        layout.addWidget(creds_group)
    
    def setup_legacy_section(self, layout):
        """セクションD: レガシーファイル互換"""
        legacy_group = QGroupBox("旧ファイル互換")
        legacy_layout = QVBoxLayout(legacy_group)
        
        # レガシーファイル状態表示
        legacy_status_layout = QHBoxLayout()
        legacy_status_layout.addWidget(QLabel("login.txt状態:"))
        self.legacy_status_label = QLabel("確認中...")
        legacy_status_layout.addWidget(self.legacy_status_label)
        legacy_status_layout.addStretch()
        legacy_layout.addLayout(legacy_status_layout)
        
        # レガシーファイル管理ボタン
        legacy_buttons_layout = QHBoxLayout()
        
        self.create_legacy_button = QPushButton("login.txt を作成")
        self.create_legacy_button.clicked.connect(self.create_legacy_file)
        legacy_buttons_layout.addWidget(self.create_legacy_button)
        
        self.view_legacy_button = QPushButton("login.txt を確認")
        self.view_legacy_button.clicked.connect(self.view_legacy_file)
        legacy_buttons_layout.addWidget(self.view_legacy_button)
        
        self.backup_legacy_button = QPushButton("login.txt をバックアップ")
        self.backup_legacy_button.clicked.connect(self.backup_legacy_file)
        legacy_buttons_layout.addWidget(self.backup_legacy_button)
        
        legacy_buttons_layout.addStretch()
        legacy_layout.addLayout(legacy_buttons_layout)
        
        # 警告設定
        self.warn_legacy_checkbox = QCheckBox("旧 login.txt 使用時に毎回警告する")
        self.warn_legacy_checkbox.setChecked(True)
        legacy_layout.addWidget(self.warn_legacy_checkbox)
        
        # 警告メッセージ
        warning_label = QLabel(
            "⚠️ 旧ファイルは平文のため非推奨。設定から安全な保存先へ移行してください。"
        )
        warning_label.setStyleSheet(
            f"color: {get_color(ThemeKey.NOTIFICATION_WARNING_TEXT)}; font-weight: bold; "
            f"padding: 10px; background-color: {get_color(ThemeKey.NOTIFICATION_WARNING_BACKGROUND)}; "
            f"border: 1px solid {get_color(ThemeKey.NOTIFICATION_WARNING_BORDER)}; border-radius: 4px;"
        )
        warning_label.setWordWrap(True)
        legacy_layout.addWidget(warning_label)
        
        layout.addWidget(legacy_group)
    
    def perform_health_check(self):
        """ヘルスチェックを実行"""
        try:
            self.health_check_result = perform_health_check()
            self.update_health_status_display()
            self.update_radio_button_states()
            self.update_current_source_display()
            # レガシーファイル状態も更新
            self.update_legacy_status()
        except Exception as e:
            logger.error(f"ヘルスチェック実行エラー: {e}")
            self.health_status_text.setText(f"ヘルスチェック失敗: {e}")
    
    def update_health_status_display(self):
        """ヘルスチェック結果の表示更新"""
        if not self.health_check_result:
            return
        
        status_text = "=== 認証ストア利用可能性 ===\n"
        
        # OSキーチェーン
        if self.health_check_result.os_ok:
            status_text += "✅ OSキーチェーン: 利用可能\n"
        else:
            error_msg = self.health_check_result.os_error or "不明なエラー"
            status_text += f"❌ OSキーチェーン: 利用不可 ({error_msg})\n"
        
        # 暗号化ファイル
        if self.health_check_result.enc_ok:
            status_text += "✅ 暗号化ファイル: 利用可能\n"
        else:
            error_msg = self.health_check_result.enc_error or "不明なエラー"
            status_text += f"❌ 暗号化ファイル: 利用不可 ({error_msg})\n"
        
        # レガシーファイル
        if self.health_check_result.legacy_exists:
            path = self.health_check_result.legacy_path or "不明"
            status_text += f"📄 レガシーファイル: 存在 ({path})\n"
        else:
            status_text += "📄 レガシーファイル: 存在しない\n"
        
        self.health_status_text.setText(status_text)
    
    def update_radio_button_states(self):
        """ラジオボタンの有効/無効状態を更新"""
        if not self.health_check_result:
            return
        
        # OSキーチェーン
        self.os_keychain_radio.setEnabled(self.health_check_result.os_ok)
        if not self.health_check_result.os_ok:
            self.os_keychain_radio.setToolTip("OSキーチェーンが利用できません")
        
        # 暗号化ファイル
        self.encrypted_file_radio.setEnabled(self.health_check_result.enc_ok)
        if not self.health_check_result.enc_ok:
            self.encrypted_file_radio.setToolTip("暗号化ファイルが利用できません")
        
        # レガシーファイル
        self.legacy_file_radio.setEnabled(self.health_check_result.legacy_exists)
        if not self.health_check_result.legacy_exists:
            self.legacy_file_radio.setToolTip("login.txtファイルが存在しません")
    
    def update_current_source_display(self):
        """現在の保存先表示を更新"""
        if not self.health_check_result:
            return
        
        preference = self.config_manager.get("autologin.credential_storage", "auto")
        current_source = decide_autologin_source(preference, self.health_check_result)
        
        source_names = {
            "os_keychain": "OSキーチェーン",
            "encrypted_file": "暗号化ファイル", 
            "legacy_file": "旧 login.txt",
            "none": "なし"
        }
        
        source_name = source_names.get(current_source, "不明")
        self.current_source_label.setText(f"現在の保存先: {source_name}")
    
    def load_current_settings(self):
        """現在の設定を読み込み"""
        try:
            # 自動ログイン有効化状態
            autologin_enabled = self.config_manager.get("autologin.autologin_enabled", False)
            self.autologin_enabled_checkbox.setChecked(autologin_enabled)
            
            # 保存先選択
            storage_pref = self.config_manager.get("autologin.credential_storage", "auto")
            storage_map = {
                "auto": 0,
                "os_keychain": 1,
                "encrypted_file": 2,
                "legacy_file": 3,
                "none": 4
            }
            button_id = storage_map.get(storage_pref, 0)
            button = self.storage_group.button(button_id)
            if button:
                button.setChecked(True)
            
            # ログインモードはデフォルトで"dice"を選択
            self.login_mode_combo.setCurrentIndex(0)  # "dice"が最初の項目
            
            # レガシー警告設定
            warn_legacy = self.config_manager.get("autologin.warn_on_legacy_file", True)
            self.warn_legacy_checkbox.setChecked(warn_legacy)
            
            # レガシーファイル状態を更新
            self.update_legacy_status()
            
            # login.txtがある場合は自動的にフィールドに読み込み
            self.try_load_from_login_txt()
            
        except Exception as e:
            logger.error(f"設定読み込みエラー: {e}")
    
    def try_load_from_login_txt(self):
        """login.txtファイルから認証情報を読み込み（利用可能な場合）"""
        try:
            from config.common import get_dynamic_file_path
            
            # login.txtまたはlogin_.txtをチェック
            login_files = [
                get_dynamic_file_path('input/login.txt'),
                get_dynamic_file_path('input/login_.txt')
            ]
            
            for login_file in login_files:
                if os.path.exists(login_file):
                    with open(login_file, 'r', encoding='utf-8') as f:
                        lines = [line.strip() for line in f.readlines() if line.strip()]
                    
                    if len(lines) >= 3:
                        username = lines[0]
                        password = lines[1]
                        login_mode = lines[2]
                        
                        # フィールドに設定（既に入力されている場合は上書きしない）
                        if not self.username_edit.text():
                            self.username_edit.setText(username)
                        
                        if not self.password_edit.text():
                            self.password_edit.setText(password)
                        
                        # ログインモードを設定
                        index = self.login_mode_combo.findData(login_mode)
                        if index >= 0:
                            self.login_mode_combo.setCurrentIndex(index)
                        
                        break  # 最初に見つかったファイルで処理を終了
                        
        except Exception as e:
            logger.debug(f"login.txtからの読み込みエラー: {e}")  # エラーレベルを下げる
    
    def save_current_settings(self):
        """現在の設定を保存"""
        try:
            # 自動ログイン有効化
            autologin_enabled = self.autologin_enabled_checkbox.isChecked()
            self.config_manager.set("autologin.autologin_enabled", autologin_enabled)
            
            # 保存先選択
            storage_map = {
                0: "auto",
                1: "os_keychain", 
                2: "encrypted_file",
                3: "legacy_file",
                4: "none"
            }
            checked_id = self.storage_group.checkedId()
            storage_pref = storage_map.get(checked_id, "auto")
            self.config_manager.set("autologin.credential_storage", storage_pref)
            
            # レガシー警告
            self.config_manager.set("autologin.warn_on_legacy_file",
                                   self.warn_legacy_checkbox.isChecked())
            
            # 設定ファイルに保存
            self.config_manager.save_to_file()
            
            # 保存成功メッセージ
            storage_name_map = {
                "auto": "自動選択",
                "os_keychain": "OSキーチェーン",
                "encrypted_file": "暗号化ファイル",
                "legacy_file": "旧 login.txt",
                "none": "保存しない"
            }
            storage_display = storage_name_map.get(storage_pref, storage_pref)
            
            QMessageBox.information(
                self, 
                "設定保存完了",
                f"自動ログイン設定を保存しました。\n\n"
                f"・自動ログイン: {'有効' if autologin_enabled else '無効'}\n"
                f"・保存先: {storage_display}\n\n"
                f"{'次回起動時から自動ログインが有効になります。' if autologin_enabled else '自動ログインは無効です。'}"
            )
            
            logger.info(f"設定保存完了: 自動ログイン={'有効' if autologin_enabled else '無効'}, 保存先={storage_pref}")
            
        except Exception as e:
            logger.error(f"設定保存エラー: {e}")
            QMessageBox.warning(self, "設定保存エラー", f"設定の保存に失敗しました: {e}")
    
    def save_credentials(self):
        """認証情報を保存"""
        try:
            # 入力検証
            username = self.username_edit.text().strip()
            password = self.password_edit.text()
            
            if not username:
                QMessageBox.warning(self, "入力エラー", "ユーザーIDを入力してください。")
                return
            
            if not password:
                QMessageBox.warning(self, "入力エラー", "パスワードを入力してください。")
                return
            
            # 認証情報オブジェクト作成
            creds = CredentialInfo(
                username=username,
                password=password,
                login_mode=self.login_mode_combo.currentData() or "dice"
            )
            
            # 保存先の決定
            if not self.health_check_result:
                QMessageBox.warning(self, "ヘルスチェック未実行", "ヘルスチェックを先に実行してください。")
                return
            
            checked_id = self.storage_group.checkedId()
            storage_map = {
                0: "auto",
                1: "os_keychain",
                2: "encrypted_file", 
                3: "legacy_file",
                4: "none"
            }
            storage_pref = storage_map.get(checked_id, "auto")
            
            if storage_pref == "none":
                QMessageBox.information(self, "保存しない", "「保存しない」が選択されています。")
                return
            
            actual_source = decide_autologin_source(storage_pref, self.health_check_result)
            
            if actual_source == "none":
                QMessageBox.warning(self, "保存先なし", "利用可能な保存先がありません。")
                return
            
            # 認証情報ストアに保存
            store = get_credential_store(actual_source)
            if not store:
                QMessageBox.warning(self, "ストア取得失敗", "認証情報ストアの取得に失敗しました。")
                return
            
            if store.save_credentials(creds):
                QMessageBox.information(self, "保存成功", f"認証情報を{actual_source}に保存しました。")
                self.save_current_settings()
                
                # パスワードフィールドをクリア
                self.password_edit.clear()
            else:
                QMessageBox.warning(self, "保存失敗", "認証情報の保存に失敗しました。")
                
        except Exception as e:
            logger.error(f"認証情報保存エラー: {e}")
            QMessageBox.warning(self, "保存エラー", f"認証情報の保存中にエラーが発生しました: {e}")
    
    def load_credentials(self):
        """認証情報を読み込み"""
        try:
            if not self.health_check_result:
                QMessageBox.warning(self, "ヘルスチェック未実行", "ヘルスチェックを先に実行してください。")
                return
            
            # 現在の設定から保存先を決定
            checked_id = self.storage_group.checkedId()
            storage_map = {
                0: "auto",
                1: "os_keychain",
                2: "encrypted_file",
                3: "legacy_file", 
                4: "none"
            }
            storage_pref = storage_map.get(checked_id, "auto")
            actual_source = decide_autologin_source(storage_pref, self.health_check_result)
            
            if actual_source == "none":
                QMessageBox.information(self, "読み込み対象なし", "読み込み可能な認証情報がありません。")
                return
            
            # 認証情報ストアから読み込み
            store = get_credential_store(actual_source)
            if not store:
                QMessageBox.warning(self, "ストア取得失敗", "認証情報ストアの取得に失敗しました。")
                return
            
            creds = store.load_credentials()
            if creds:
                self.username_edit.setText(creds.username)
                self.password_edit.setText(creds.password)
                # ログインモードコンボボックスの選択を設定
                login_mode = creds.login_mode or "dice"
                index = self.login_mode_combo.findData(login_mode)
                if index >= 0:
                    self.login_mode_combo.setCurrentIndex(index)
                QMessageBox.information(self, "読み込み成功", f"認証情報を{actual_source}から読み込みました。")
            else:
                QMessageBox.information(self, "認証情報なし", f"{actual_source}に認証情報が見つかりませんでした。")
                
        except Exception as e:
            logger.error(f"認証情報読み込みエラー: {e}")
            QMessageBox.warning(self, "読み込みエラー", f"認証情報の読み込み中にエラーが発生しました: {e}")
    
    def delete_credentials(self):
        """認証情報を削除"""
        try:
            # 削除確認
            reply = QMessageBox.question(
                self, "削除確認", 
                "保存された認証情報を削除しますか？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            if not self.health_check_result:
                QMessageBox.warning(self, "ヘルスチェック未実行", "ヘルスチェックを先に実行してください。")
                return
            
            # 現在の設定から保存先を決定
            checked_id = self.storage_group.checkedId()
            storage_map = {
                0: "auto",
                1: "os_keychain",
                2: "encrypted_file",
                3: "legacy_file",
                4: "none"
            }
            storage_pref = storage_map.get(checked_id, "auto")
            actual_source = decide_autologin_source(storage_pref, self.health_check_result)
            
            if actual_source == "none":
                QMessageBox.information(self, "削除対象なし", "削除可能な認証情報がありません。")
                return
            
            # 認証情報ストアから削除
            store = get_credential_store(actual_source)
            if not store:
                QMessageBox.warning(self, "ストア取得失敗", "認証情報ストアの取得に失敗しました。")
                return
            
            if store.delete_credentials():
                QMessageBox.information(self, "削除成功", f"認証情報を{actual_source}から削除しました。")
                # フォームをクリア
                self.username_edit.clear()
                self.password_edit.clear()
                self.login_mode_combo.setCurrentIndex(0)  # 最初の項目に戻す
            else:
                QMessageBox.warning(self, "削除失敗", "認証情報の削除に失敗しました。")
                
        except Exception as e:
            logger.error(f"認証情報削除エラー: {e}")
            QMessageBox.warning(self, "削除エラー", f"認証情報の削除中にエラーが発生しました: {e}")
    
    def open_rde_page(self):
        """メインアプリでRDEページを開く"""
        try:
            from qt_compat.widgets import QApplication
            app = QApplication.instance()
            
            if not app:
                QMessageBox.warning(self, "アプリケーション未検出", "メインアプリケーションが見つかりません。")
                return
            
            # メインブラウザウィンドウを検索
            main_browser = None
            for widget in app.allWidgets():
                if hasattr(widget, 'webview') and hasattr(widget, 'login_manager'):
                    main_browser = widget
                    break
            
            if not main_browser:
                QMessageBox.warning(self, "WebView未検出", "メインブラウザウィンドウが見つかりません。")
                return
            
            # RDEページに移動
            from config.site_rde import URLS
            from qt_compat.core import QUrl
            
            rde_url = URLS["web"]["base"]
            main_browser.webview.setUrl(QUrl(rde_url))
            
            # 成功メッセージ
            QMessageBox.information(
                self,
                "RDEページを開いています",
                f"メインアプリで RDE ページを開いています:\n{rde_url}\n\n"
                "ページが完全に読み込まれてからテストログインを実行してください。"
            )
            
            logger.info(f"RDEページを開きました: {rde_url}")
            
        except Exception as e:
            logger.error(f"RDEページオープンエラー: {e}")
            QMessageBox.warning(self, "エラー", f"RDEページを開けませんでした: {e}")
    
    def apply_settings(self):
        """設定を適用"""
        try:
            self.save_current_settings()
            logger.info("自動ログイン設定が適用されました")
        except Exception as e:
            logger.error(f"自動ログイン設定適用エラー: {e}")
            raise
    
    # 下位互換性・テスト用の別名メソッド
    def load_settings(self):
        """設定読み込み（load_current_settingsの別名）"""
        return self.load_current_settings()
    
    def save_settings(self):
        """設定保存（save_current_settingsの別名）"""
        return self.save_current_settings()
    
    # === レガシーファイル管理メソッド ===
    
    def update_legacy_status(self):
        """レガシーファイル状態の更新"""
        try:
            from config.common import LOGIN_FILE
            import os
            
            if os.path.exists(LOGIN_FILE):
                # ファイルサイズとタイムスタンプを確認
                stat = os.stat(LOGIN_FILE)
                size = stat.st_size
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
                self.legacy_status_label.setText(f"✅ 存在 ({size}バイト, 更新:{mtime})")
                self.legacy_status_label.setStyleSheet("color: green;")
                
                # ボタン状態を更新
                self.create_legacy_button.setText("login.txt を更新")
                self.view_legacy_button.setEnabled(True)
                self.backup_legacy_button.setEnabled(True)
            else:
                self.legacy_status_label.setText("❌ 存在しません")
                self.legacy_status_label.setStyleSheet("color: red;")
                
                # ボタン状態を更新
                self.create_legacy_button.setText("login.txt を作成")
                self.view_legacy_button.setEnabled(False)
                self.backup_legacy_button.setEnabled(False)
                
        except Exception as e:
            self.legacy_status_label.setText(f"❌ 確認エラー: {e}")
            self.legacy_status_label.setStyleSheet("color: red;")
    
    def create_legacy_file(self):
        """login.txtファイルを作成"""
        try:
            from config.common import LOGIN_FILE
            import os
            
            # 現在入力されている認証情報を取得
            username = self.username_edit.text().strip()
            password = self.password_edit.text()
            login_mode = self.login_mode_combo.currentData() or "dice"
            
            if not username or not password:
                QMessageBox.warning(
                    self, 
                    "入力エラー", 
                    "ユーザーIDとパスワードを入力してからlogin.txtを作成してください。"
                )
                return
            
            # 既存ファイルがある場合は確認
            if os.path.exists(LOGIN_FILE):
                reply = QMessageBox.question(
                    self,
                    "ファイル更新確認",
                    f"login.txt は既に存在します。上書きしますか？\n\nパス: {LOGIN_FILE}",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return
            
            # ディレクトリを作成（存在しない場合）
            os.makedirs(os.path.dirname(LOGIN_FILE), exist_ok=True)
            
            # login.txtファイルを作成
            with open(LOGIN_FILE, 'w', encoding='utf-8') as f:
                f.write(f"{username}\n")
                f.write(f"{password}\n")
                if login_mode:
                    f.write(f"{login_mode}\n")
            
            self.update_legacy_status()
            QMessageBox.information(
                self,
                "作成完了",
                f"login.txt を作成しました。\n\nパス: {LOGIN_FILE}\n\n"
                "⚠️ このファイルは平文で保存されます。\n"
                "セキュリティのため、OSキーチェーンまたは暗号化ファイルの使用を推奨します。"
            )
            
        except Exception as e:
            logger.error(f"login.txt作成エラー: {e}")
            QMessageBox.warning(self, "作成エラー", f"login.txtの作成に失敗しました: {e}")
    
    def view_legacy_file(self):
        """login.txtファイルの内容を確認"""
        try:
            from config.common import LOGIN_FILE
            
            if not os.path.exists(LOGIN_FILE):
                QMessageBox.warning(self, "ファイル不存在", "login.txt が見つかりません。")
                return
            
            from functions.common_funcs import read_login_info
            username, password, login_mode = read_login_info()
            
            # パスワードをマスク
            masked_password = "*" * len(password) if password else "(空)"
            
            content = f"ファイルパス: {LOGIN_FILE}\n\n"
            content += f"ユーザーID: {username or '(空)'}\n"
            content += f"パスワード: {masked_password}\n"
            content += f"ログインモード: {login_mode or '(空)'}"
            
            QMessageBox.information(self, "login.txt 内容確認", content)
            
        except Exception as e:
            logger.error(f"login.txt確認エラー: {e}")
            QMessageBox.warning(self, "確認エラー", f"login.txtの確認に失敗しました: {e}")
    
    def backup_legacy_file(self):
        """login.txtファイルをバックアップ"""
        try:
            from config.common import LOGIN_FILE
            import shutil
            from datetime import datetime
            
            if not os.path.exists(LOGIN_FILE):
                QMessageBox.warning(self, "ファイル不存在", "login.txt が見つかりません。")
                return
            
            # バックアップファイル名（タイムスタンプ付き）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"{LOGIN_FILE}.backup_{timestamp}"
            
            # バックアップ実行
            shutil.copy2(LOGIN_FILE, backup_file)
            
            QMessageBox.information(
                self,
                "バックアップ完了",
                f"login.txt をバックアップしました。\n\nバックアップファイル:\n{backup_file}"
            )
            
        except Exception as e:
            logger.error(f"login.txtバックアップエラー: {e}")
            QMessageBox.warning(self, "バックアップエラー", f"login.txtのバックアップに失敗しました: {e}")
