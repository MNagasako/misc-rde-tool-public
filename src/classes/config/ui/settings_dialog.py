"""
設定ダイアログ - ARIM RDE Tool
プロキシ設定、ネットワーク設定、アプリケーション設定の統合UI

新構造対応: REFACTOR_PLAN_01.md準拠
- core: 設定管理ロジック
- ui: ユーザーインターフェース
- util: 設定ユーティリティ
- conf: 設定ファイル管理
"""

import sys
import logging
from typing import Dict, Any, Optional

try:
    # WebEngine初期化問題の回避
    from qt_compat import initialize_webengine
    from qt_compat.core import Qt

    # WebEngine初期化
    initialize_webengine()
    
    from qt_compat.widgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QMessageBox, QWidget,
        QScrollArea, QGroupBox, QGridLayout, QApplication
    )
    from qt_compat.core import Qt, QTimer
    from qt_compat.gui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    # ダミークラス定義
    class QDialog: pass
    class QWidget: pass
    class QApplication: pass

# ログ設定
logger = logging.getLogger(__name__)

class SettingsDialog(QDialog):
    """設定ダイアログメインクラス"""
    
    def __init__(self, parent=None, bearer_token=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.bearer_token = bearer_token
        self.setup_ui()
        
    def setup_ui(self):
        """UI初期化"""
        self.setWindowTitle("ARIM RDE Tool - アプリケーション設定")
        self.setModal(True)
        
        # 画面サイズの90%に設定
        if PYQT5_AVAILABLE:
            # PySide6対応
            from qt_compat import get_screen_geometry
            screen_rect = get_screen_geometry(self)
            width = int(screen_rect.width() * 0.9)
            height = int(screen_rect.height() * 0.9)
            self.resize(width, height)
            
            # 画面中央に配置
            self.move(
                (screen_rect.width() - width) // 2,
                (screen_rect.height() - height) // 2
            )
        else:
            self.resize(800, 600)
        
        # メインレイアウト
        layout = QVBoxLayout(self)
        
        # スクロールエリアでタブウィジェットを囲む
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # タブウィジェット
        self.tab_widget = QTabWidget()
        scroll_area.setWidget(self.tab_widget)
        layout.addWidget(scroll_area)
        
        # プロキシ設定タブ
        logger.info("setup_ui: プロキシ設定タブ作成開始")
        self.setup_proxy_tab()
        logger.info("setup_ui: プロキシ設定タブ作成完了")
        
        # ネットワーク設定タブ
        logger.info("setup_ui: ネットワーク設定タブ作成開始")
        self.setup_network_tab()
        logger.info("setup_ui: ネットワーク設定タブ作成完了")
        
        # アプリケーション設定タブ
        logger.info("setup_ui: アプリケーション設定タブ作成開始")
        self.setup_application_tab()
        logger.info("setup_ui: アプリケーション設定タブ作成完了")
        
        # 自動ログインタブ
        logger.info("setup_ui: 自動ログインタブ作成開始")
        self.setup_autologin_tab()
        logger.info("setup_ui: 自動ログインタブ作成完了")
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        self.apply_button = QPushButton("適用")
        self.apply_button.clicked.connect(self.apply_settings)
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept_settings)
        
        self.cancel_button = QPushButton("キャンセル")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
    def setup_proxy_tab(self):
        """プロキシ設定タブ"""
        try:
            from classes.config.ui.proxy_settings_widget import ProxySettingsWidget
            proxy_widget = ProxySettingsWidget(self)
            
            # プロキシ設定ウィジェットをスクロールエリアでラップ
            proxy_scroll = QScrollArea()
            proxy_scroll.setWidgetResizable(True)
            proxy_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            proxy_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            proxy_scroll.setWidget(proxy_widget)
            
            self.proxy_widget = proxy_widget
            self.tab_widget.addTab(proxy_scroll, "プロキシ設定")
        except ImportError as e:
            logger.warning(f"プロキシ設定ウィジェットのインポートに失敗: {e}")
            # フォールバック用の簡易プロキシ設定
            proxy_widget = self.create_fallback_proxy_widget()
            
            # フォールバック用もスクロールエリアでラップ
            proxy_scroll = QScrollArea()
            proxy_scroll.setWidgetResizable(True)
            proxy_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            proxy_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            proxy_scroll.setWidget(proxy_widget)
            
            self.proxy_widget = proxy_widget
            self.tab_widget.addTab(proxy_scroll, "プロキシ設定")
            
    def create_fallback_proxy_widget(self):
        """フォールバック用簡易プロキシ設定ウィジェット"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # タイトル
        title_label = QLabel("プロキシ設定")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        info_label = QLabel(
            "プロキシ設定はアプリケーション起動時に自動検出・適用されます。\n"
            "手動設定が必要な場合は、config/network.json を直接編集してください。"
        )
        layout.addWidget(info_label)
        
        # 現在の設定表示
        status_group = QGroupBox("現在のプロキシ状態")
        status_layout = QVBoxLayout(status_group)
        
        self.proxy_status_label = QLabel("読み込み中...")
        status_layout.addWidget(self.proxy_status_label)
        
        layout.addWidget(status_group)
        
        # 設定更新ボタン
        refresh_button = QPushButton("設定を再読み込み")
        refresh_button.clicked.connect(self.refresh_proxy_status)
        layout.addWidget(refresh_button)
        
        layout.addStretch()
        
        # 初回読み込み
        QTimer.singleShot(100, self.refresh_proxy_status)
        
        return widget
        
    def refresh_proxy_status(self):
        """プロキシ状態を更新"""
        try:
            from net.session_manager import get_proxy_config
            config = get_proxy_config()
            
            if config:
                mode = config.get('mode', 'UNKNOWN')
                if mode == 'SYSTEM':
                    status_text = "🌐 システムプロキシ使用"
                elif mode == 'DIRECT':
                    status_text = "🔗 直接接続"
                elif mode == 'HTTP':
                    status_text = "🔧 カスタムHTTPプロキシ使用"
                else:
                    status_text = f"❓ モード: {mode}"
                    
                self.proxy_status_label.setText(status_text)
            else:
                self.proxy_status_label.setText("❌ プロキシ設定を取得できませんでした")
                
        except Exception as e:
            logger.error(f"プロキシ状態取得エラー: {e}")
            self.proxy_status_label.setText(f"❌ エラー: {e}")
            
    def setup_network_tab(self):
        """ネットワーク設定タブ"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # タイトル
        title_label = QLabel("ネットワーク設定")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 接続タイムアウト設定
        timeout_group = QGroupBox("接続設定")
        timeout_layout = QGridLayout(timeout_group)
        
        timeout_layout.addWidget(QLabel("HTTPタイムアウト:"), 0, 0)
        timeout_layout.addWidget(QLabel("30秒"), 0, 1)
        
        timeout_layout.addWidget(QLabel("WebViewタイムアウト:"), 1, 0)
        timeout_layout.addWidget(QLabel("60秒"), 1, 1)
        
        layout.addWidget(timeout_group)
        
        # SSL設定
        ssl_group = QGroupBox("SSL設定")
        ssl_layout = QVBoxLayout(ssl_group)
        
        ssl_info = QLabel(
            "SSL証明書の検証設定はプロキシ環境に応じて自動調整されます。\n"
            "企業プロキシ環境では証明書検証が無効化される場合があります。"
        )
        ssl_layout.addWidget(ssl_info)
        
        layout.addWidget(ssl_group)
        
        layout.addStretch()
        
        # ネットワーク設定タブもスクロール対応
        network_scroll = QScrollArea()
        network_scroll.setWidgetResizable(True)
        network_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        network_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        network_scroll.setWidget(widget)
        
        self.tab_widget.addTab(network_scroll, "ネットワーク")
        
    def setup_application_tab(self):
        """アプリケーション設定タブ"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # タイトル
        title_label = QLabel("アプリケーション設定")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # UI設定
        ui_group = QGroupBox("ユーザーインターフェース")
        ui_layout = QVBoxLayout(ui_group)
        
        ui_info = QLabel(
            "・フォントサイズ: システム設定に従う\n"
            "・テーマ: システムテーマを使用\n"
            "・言語: 日本語"
        )
        ui_layout.addWidget(ui_info)
        
        layout.addWidget(ui_group)
        
        # ログ設定
        log_group = QGroupBox("ログ設定")
        log_layout = QVBoxLayout(log_group)
        
        log_info = QLabel(
            "ログレベル: INFO\n"
            "ログファイル: output/log/ ディレクトリに保存"
        )
        log_layout.addWidget(log_info)
        
        layout.addWidget(log_group)
        
        layout.addStretch()
        
        # アプリケーション設定タブもスクロール対応
        app_scroll = QScrollArea()
        app_scroll.setWidgetResizable(True)
        app_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        app_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        app_scroll.setWidget(widget)
        
        self.tab_widget.addTab(app_scroll, "アプリケーション")
        
    def setup_autologin_tab(self):
        """自動ログインタブ"""
        logger.info("setup_autologin_tab: 開始")
        try:
            logger.info("setup_autologin_tab: AutoLoginTabWidgetのインポートを試行")
            from classes.config.ui.autologin_tab_widget import AutoLoginTabWidget
            logger.info("setup_autologin_tab: AutoLoginTabWidgetインポート成功")
            
            logger.info("setup_autologin_tab: AutoLoginTabWidgetの作成を試行")
            autologin_widget = AutoLoginTabWidget(self)
            logger.info("setup_autologin_tab: AutoLoginTabWidget作成成功")
            
            # 自動ログインウィジェットをスクロールエリアでラップ
            logger.info("setup_autologin_tab: スクロールエリアの作成を試行")
            autologin_scroll = QScrollArea()
            autologin_scroll.setWidgetResizable(True)
            autologin_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            autologin_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            autologin_scroll.setWidget(autologin_widget)
            logger.info("setup_autologin_tab: スクロールエリア作成成功")
            
            self.autologin_widget = autologin_widget
            self.tab_widget.addTab(autologin_scroll, "自動ログイン")
            logger.info("setup_autologin_tab: 自動ログインタブ追加成功")
            
        except ImportError as e:
            logger.warning(f"自動ログインタブウィジェットのインポートに失敗: {e}")
            # フォールバック用の簡易自動ログイン設定
            logger.info("setup_autologin_tab: フォールバックウィジェット作成開始")
            autologin_widget = self.create_fallback_autologin_widget()
            
            # フォールバック用もスクロールエリアでラップ
            autologin_scroll = QScrollArea()
            autologin_scroll.setWidgetResizable(True)
            autologin_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            autologin_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            autologin_scroll.setWidget(autologin_widget)
            
            self.autologin_widget = autologin_widget
            self.tab_widget.addTab(autologin_scroll, "自動ログイン")
            logger.info("setup_autologin_tab: フォールバック自動ログインタブ追加成功")
            
        except Exception as e:
            logger.error(f"自動ログインタブ作成エラー: {e}")
            import traceback
            logger.error(f"自動ログインタブ作成エラー詳細: {traceback.format_exc()}")
            
            # エラー表示のみのタブ
            error_widget = QWidget()
            error_layout = QVBoxLayout(error_widget)
            error_label = QLabel(f"自動ログインタブの作成に失敗しました: {e}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            error_layout.addWidget(error_label)
            error_layout.addStretch()
            
            self.tab_widget.addTab(error_widget, "自動ログイン")
            logger.error("setup_autologin_tab: エラー表示タブ追加完了")
            
    def create_fallback_autologin_widget(self):
        """フォールバック用簡易自動ログイン設定ウィジェット"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # タイトル
        title_label = QLabel("自動ログイン設定")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        info_label = QLabel(
            "自動ログイン機能の詳細設定はライブラリ依存関係の問題により利用できません。\n"
            "基本的な自動ログイン機能は既存の login.txt で動作します。\n"
            "\n"
            "高度な認証情報管理を利用するには：\n"
            "1. pip install keyring\n"
            "2. pip install pycryptodomex\n"
            "3. アプリケーションを再起動"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 現在の設定表示
        status_group = QGroupBox("現在の状態")
        status_layout = QVBoxLayout(status_group)
        
        try:
            from config.common import LOGIN_FILE
            import os
            if os.path.exists(LOGIN_FILE):
                status_text = f"✅ 従来のlogin.txtが存在: {LOGIN_FILE}"
            else:
                status_text = f"❌ login.txtが存在しません: {LOGIN_FILE}"
        except Exception as e:
            status_text = f"❌ ファイルチェックエラー: {e}"
        
        self.autologin_status_label = QLabel(status_text)
        status_layout.addWidget(self.autologin_status_label)
        
        layout.addWidget(status_group)
        
        layout.addStretch()
        
        return widget
        
    def apply_settings(self):
        """設定を適用"""
        try:
            # プロキシ設定の適用
            if hasattr(self.proxy_widget, 'apply_settings'):
                self.proxy_widget.apply_settings()
            
            # 自動ログイン設定の適用
            if hasattr(self.autologin_widget, 'apply_settings'):
                self.autologin_widget.apply_settings()
                
            QMessageBox.information(self, "設定適用", "設定が適用されました。")
            
        except Exception as e:
            logger.error(f"設定適用エラー: {e}")
            QMessageBox.warning(self, "エラー", f"設定の適用に失敗しました: {e}")
            
    def accept_settings(self):
        """設定を適用して閉じる"""
        self.apply_settings()
        self.accept()


def run_settings_logic(parent=None, bearer_token=None):
    """設定ダイアログを開く（旧インターフェース互換）"""
    try:
        if not PYQT5_AVAILABLE:
            if parent:
                parent.show_error("PyQt5が利用できないため、設定ダイアログを開けません。")
            return
            
        dialog = SettingsDialog(parent, bearer_token)
        dialog.exec()
        
    except Exception as e:
        logger.error(f"設定ダイアログエラー: {e}")
        if parent:
            try:
                from qt_compat.widgets import QMessageBox
                QMessageBox.warning(parent, "エラー", f"設定ダイアログの起動に失敗しました: {e}")
            except:
                logger.error("設定ダイアログエラー: %s", e)


def create_settings_widget(parent=None, bearer_token=None):
    """設定ウィジェットを作成（ウィジェット形式）"""
    try:
        return SettingsDialog(parent, bearer_token)
    except Exception as e:
        logger.error(f"設定ウィジェット作成エラー: {e}")
        return None
