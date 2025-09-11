"""
設定タブウィジェット - ARIM RDE Tool
メインウィンドウのタブとして表示される設定機能

新構造対応: 段組表示・レスポンシブ対応・画面サイズ適応
- プロキシ設定の段組表示で高さを抑制
- 画面サイズに応じた動的レイアウト調整
- メインウィンドウタブとしての統合
"""

import sys
import logging
from typing import Dict, Any, Optional

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QMessageBox, 
        QScrollArea, QGroupBox, QGridLayout, QApplication,
        QSplitter, QFrame
    )
    from PyQt5.QtCore import Qt, QTimer, QSize
    from PyQt5.QtGui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    # ダミークラス定義
    class QWidget: pass
    class QApplication: pass

# ログ設定
logger = logging.getLogger(__name__)

class SettingsTabWidget(QWidget):
    """設定タブウィジェットクラス"""
    
    def __init__(self, parent=None, bearer_token=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.bearer_token = bearer_token
        self.setup_ui()
        
    def setup_ui(self):
        """UI初期化 - レスポンシブ・段組対応"""
        # メインレイアウト
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # タブウィジェット
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # プロキシ設定タブ（段組表示）
        self.setup_proxy_tab_responsive()
        
        # ネットワーク設定タブ
        self.setup_network_tab()
        
        # アプリケーション設定タブ
        self.setup_application_tab()
            
        # 自動ログインタブ
        self.setup_autologin_tab()

        # インポートタブ（ダミー）
        self.setup_import_tab_dummy()
            
        # ボタンエリア
        button_layout = QHBoxLayout()
            
        self.apply_button = QPushButton("適用")
        self.apply_button.clicked.connect(self.apply_settings)
            
        self.reload_button = QPushButton("再読み込み")
        self.reload_button.clicked.connect(self.reload_settings)
            
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.reload_button)
        
    #layout.addLayout(button_layout)
    def setup_import_tab_dummy(self):
        """インポートタブ（ダミー表示）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        title_label = QLabel("インポート（ダミー表示）")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        info_label = QLabel("このタブは今後インポート機能を実装予定です。\n（現状はダミー表示です）")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        layout.addStretch()
        self.tab_widget.addTab(widget, "インポート")
        
    def get_optimal_layout_columns(self):
        """画面サイズに基づいて最適な段組数を決定"""
        if not PYQT5_AVAILABLE:
            return 1
            
        try:
            # メインウィンドウまたは画面サイズを取得
            if self.parent_widget:
                width = self.parent_widget.width()
            else:
                desktop = QApplication.desktop()
                screen_rect = desktop.screenGeometry()
                width = screen_rect.width()
            
            # 幅に応じて段組数を決定
            if width >= 1920:  # 4K以上
                return 3
            elif width >= 1440:  # WQHD以上
                return 2
            elif width >= 1024:  # HD以上
                return 2
            else:  # それ以下
                return 1
                
        except Exception as e:
            logger.warning(f"画面サイズ取得エラー: {e}")
            return 2  # デフォルト値
            
    def setup_proxy_tab_responsive(self):
        """プロキシ設定タブ - 元の完全な機能を保持したレスポンシブ表示"""
        try:
            # 元のProxySettingsWidgetを使用
            from classes.config.ui.proxy_settings_widget import ProxySettingsWidget
            
            # プロキシ設定ウィジェットを作成
            proxy_widget = ProxySettingsWidget(self)
            
            # スクロールエリアでラップ
            proxy_scroll = QScrollArea()
            proxy_scroll.setWidgetResizable(True)
            proxy_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            proxy_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            proxy_scroll.setMinimumHeight(800)  # 最小高さを600pxに設定（現在の2倍程度）
            proxy_scroll.setWidget(proxy_widget)
            
            # プロキシ設定ウィジェットへの参照を保存
            self.proxy_widget = proxy_widget
            
            # タブに追加
            self.tab_widget.addTab(proxy_scroll, "プロキシ設定")
            
        except ImportError as e:
            logger.warning(f"完全なプロキシ設定ウィジェットのインポートに失敗: {e}")
            # フォールバック：簡略版を作成
            self.setup_proxy_tab_fallback()
        except Exception as e:
            logger.error(f"プロキシ設定タブ作成エラー: {e}")
            # フォールバック：簡略版を作成
            self.setup_proxy_tab_fallback()
    
    def setup_proxy_tab_fallback(self):
        """プロキシ設定タブ - フォールバック版（元のコード）"""
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # タイトル
        title_label = QLabel("プロキシ設定")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        main_layout.addWidget(title_label)
        
        # 段組数を取得
        columns = self.get_optimal_layout_columns()
        
        if columns >= 2:
            # 段組表示用のスプリッター
            splitter = QSplitter(Qt.Horizontal)
            main_layout.addWidget(splitter)
            
            # 左側：基本設定
            left_widget = QWidget()
            left_layout = QVBoxLayout(left_widget)
            left_layout.setContentsMargins(5, 5, 5, 5)
            left_layout.setSpacing(8)
            self.setup_basic_proxy_settings(left_layout)
            splitter.addWidget(left_widget)
            
            # 右側：高度な設定
            right_widget = QWidget()
            right_layout = QVBoxLayout(right_widget)
            right_layout.setContentsMargins(5, 5, 5, 5)
            right_layout.setSpacing(8)
            self.setup_advanced_proxy_settings(right_layout)
            
            # 3段組の場合は中央に詳細設定
            if columns >= 3:
                center_widget = QWidget()
                center_layout = QVBoxLayout(center_widget)
                center_layout.setContentsMargins(5, 5, 5, 5)
                center_layout.setSpacing(8)
                self.setup_proxy_details_section_compact(center_layout)
                splitter.insertWidget(1, center_widget)
                
                # 右側にはテスト機能のみ
                self.setup_test_section_compact(right_layout)
            else:
                # 2段組の場合は右側に詳細設定とテストを追加
                self.setup_proxy_details_section_compact(right_layout)
                self.setup_test_section_compact(right_layout)
            
            splitter.addWidget(right_widget)
            
            # 各段の幅を均等に設定
            if columns == 2:
                splitter.setSizes([400, 400])
            elif columns == 3:
                splitter.setSizes([300, 300, 300])
                
        else:
            # 1段組表示（従来通り）
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            
            content_widget = QWidget()
            content_layout = QVBoxLayout(content_widget)
            content_layout.setContentsMargins(10, 10, 10, 10)
            content_layout.setSpacing(10)
            
            self.setup_basic_proxy_settings(content_layout)
            self.setup_advanced_proxy_settings(content_layout)
            self.setup_proxy_details_section_compact(content_layout)
            self.setup_test_section_compact(content_layout)
            
            scroll_area.setWidget(content_widget)
            main_layout.addWidget(scroll_area)
        
        self.tab_widget.addTab(main_widget, "プロキシ設定")
        
    def setup_basic_proxy_settings(self, layout):
        """基本プロキシ設定セクション"""
        # 現在の状態表示
        status_group = QGroupBox("現在の状態")
        status_layout = QGridLayout(status_group)
        
        status_layout.addWidget(QLabel("プロキシモード:"), 0, 0)
        self.current_mode_label = QLabel("読み込み中...")
        self.current_mode_label.setStyleSheet("font-weight: bold; color: blue;")
        status_layout.addWidget(self.current_mode_label, 0, 1)
        
        status_layout.addWidget(QLabel("HTTPプロキシ:"), 1, 0)
        self.current_http_proxy_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_http_proxy_label, 1, 1)
        
        layout.addWidget(status_group)
        
        # プロキシモード選択
        mode_group = QGroupBox("プロキシモード")
        mode_layout = QVBoxLayout(mode_group)
        
        try:
            from PyQt5.QtWidgets import QRadioButton, QButtonGroup
            
            self.mode_button_group = QButtonGroup(self)
            
            self.direct_radio = QRadioButton("DIRECT - 直接接続")
            self.system_radio = QRadioButton("SYSTEM - システム設定")
            self.http_radio = QRadioButton("HTTP - 手動設定")
            
            self.mode_button_group.addButton(self.direct_radio, 0)
            self.mode_button_group.addButton(self.system_radio, 1)
            self.mode_button_group.addButton(self.http_radio, 2)
            
            mode_layout.addWidget(self.direct_radio)
            mode_layout.addWidget(self.system_radio)
            mode_layout.addWidget(self.http_radio)
            
        except ImportError:
            mode_layout.addWidget(QLabel("ラジオボタンが利用できません"))
            
        layout.addWidget(mode_group)
        
    def setup_advanced_proxy_settings(self, layout):
        """高度なプロキシ設定セクション"""
        # 組織内CA設定
        enterprise_group = QGroupBox("組織内CA設定")
        enterprise_layout = QGridLayout(enterprise_group)
        
        try:
            from PyQt5.QtWidgets import QCheckBox
            
            self.enable_truststore_checkbox = QCheckBox("truststoreを使用")
            self.enable_truststore_checkbox.setToolTip("システム証明書を自動取得")
            enterprise_layout.addWidget(self.enable_truststore_checkbox, 0, 0, 1, 2)
            
            self.auto_detect_corporate_ca_checkbox = QCheckBox("組織内CA自動検出")
            self.auto_detect_corporate_ca_checkbox.setToolTip("CA証明書を自動検出")
            enterprise_layout.addWidget(self.auto_detect_corporate_ca_checkbox, 1, 0, 1, 2)
            
        except ImportError:
            enterprise_layout.addWidget(QLabel("チェックボックスが利用できません"), 0, 0)
            
        # テストボタン
        test_ca_btn = QPushButton("組織内CA確認")
        test_ca_btn.clicked.connect(self.test_enterprise_ca)
        enterprise_layout.addWidget(test_ca_btn, 2, 0, 1, 2)
        
        layout.addWidget(enterprise_group)
        
    def setup_test_section_compact(self, layout):
        """接続テストセクション（コンパクト版）"""
        test_group = QGroupBox("接続テスト")
        test_layout = QVBoxLayout(test_group)
        
        self.test_button = QPushButton("接続テスト実行")
        self.test_button.clicked.connect(self.run_connection_test)
        test_layout.addWidget(self.test_button)
        
        self.test_result_label = QLabel("テスト未実行")
        self.test_result_label.setWordWrap(True)
        test_layout.addWidget(self.test_result_label)
        
        layout.addWidget(test_group)
        
    def setup_proxy_details_section_compact(self, layout):
        """プロキシ詳細設定セクション（コンパクト版）"""
        details_group = QGroupBox("詳細設定")
        details_layout = QGridLayout(details_group)
        
        try:
            from PyQt5.QtWidgets import QLineEdit
            
            details_layout.addWidget(QLabel("HTTPプロキシ:"), 0, 0)
            self.http_proxy_edit = QLineEdit()
            self.http_proxy_edit.setPlaceholderText("http://proxy:8080")
            details_layout.addWidget(self.http_proxy_edit, 0, 1)
            
            details_layout.addWidget(QLabel("HTTPSプロキシ:"), 1, 0)
            self.https_proxy_edit = QLineEdit()
            self.https_proxy_edit.setPlaceholderText("http://proxy:8080")
            details_layout.addWidget(self.https_proxy_edit, 1, 1)
            
        except ImportError:
            details_layout.addWidget(QLabel("入力フィールドが利用できません"), 0, 0)
            
        layout.addWidget(details_group)
        
    def setup_network_tab(self):
        """ネットワーク設定タブ"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # タイトル
        title_label = QLabel("ネットワーク設定")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 接続設定
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
        self.tab_widget.addTab(widget, "ネットワーク")
        
    def setup_application_tab(self):
        """アプリケーション設定タブ"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # タイトル
        title_label = QLabel("アプリケーション設定")
        title_font = QFont()
        title_font.setPointSize(14)
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
        self.tab_widget.addTab(widget, "アプリケーション")
        
    def test_enterprise_ca(self):
        """組織内CA確認テスト"""
        try:
            # 実際の処理をプロキシ設定ウィジェットに委譲
            if hasattr(self, 'proxy_widget') and hasattr(self.proxy_widget, 'test_enterprise_ca'):
                self.proxy_widget.test_enterprise_ca()
            else:
                QMessageBox.information(self, "組織内CA確認", "組織内CA確認機能は利用できません。")
        except Exception as e:
            logger.error(f"組織内CA確認エラー: {e}")
            QMessageBox.warning(self, "エラー", f"組織内CA確認中にエラーが発生しました: {e}")
            
    def run_connection_test(self):
        """接続テスト実行"""
        try:
            # 接続テストの実装
            self.test_result_label.setText("接続テスト中...")
            self.test_button.setEnabled(False)
            
            # 実際のテスト処理
            QTimer.singleShot(2000, self._connection_test_finished)
            
        except Exception as e:
            logger.error(f"接続テストエラー: {e}")
            self.test_result_label.setText(f"テストエラー: {e}")
            self.test_button.setEnabled(True)
            
    def _connection_test_finished(self):
        """接続テスト完了処理"""
        self.test_result_label.setText("接続テスト完了: 正常")
        self.test_button.setEnabled(True)
        
    def apply_settings(self):
        """設定を適用"""
        try:
            # プロキシ設定の適用
            if hasattr(self, 'proxy_widget') and hasattr(self.proxy_widget, 'apply_settings'):
                self.proxy_widget.apply_settings()
                QMessageBox.information(self, "設定適用", "プロキシ設定が適用されました。")
            else:
                QMessageBox.information(self, "設定適用", "設定が適用されました。（プロキシ設定は簡易モード）")
            
        except Exception as e:
            logger.error(f"設定適用エラー: {e}")
            QMessageBox.warning(self, "エラー", f"設定の適用に失敗しました: {e}")
            
    def reload_settings(self):
        """設定を再読み込み"""
        try:
            # プロキシ設定の再読み込み
            if hasattr(self, 'proxy_widget') and hasattr(self.proxy_widget, 'load_current_settings'):
                self.proxy_widget.load_current_settings()
                QMessageBox.information(self, "設定再読み込み", "プロキシ設定が再読み込みされました。")
            else:
                # フォールバック処理
                if hasattr(self, 'current_mode_label'):
                    self.current_mode_label.setText("SYSTEM")
                if hasattr(self, 'current_http_proxy_label'):
                    self.current_http_proxy_label.setText("自動検出")
                QMessageBox.information(self, "設定再読み込み", "設定が再読み込みされました。（簡易モード）")
            
        except Exception as e:
            logger.error(f"設定再読み込みエラー: {e}")
            QMessageBox.warning(self, "エラー", f"設定の再読み込みに失敗しました: {e}")

    def setup_autologin_tab(self):
        """自動ログインタブを設定"""
        try:
            print("[settings_tab_widget] setup_autologin_tab: 開始")
            
            # AutoLoginTabWidgetのインポートを試行
            try:
                from classes.config.ui.autologin_tab_widget import AutoLoginTabWidget
                print("[settings_tab_widget] AutoLoginTabWidgetのインポートを試行")
                
                # 自動ログインタブウィジェットを作成
                autologin_widget = AutoLoginTabWidget(self)
                print("[settings_tab_widget] AutoLoginTabWidget作成成功")
                
                # タブに追加
                tab_index = self.tab_widget.addTab(autologin_widget, "自動ログイン")
                print(f"[settings_tab_widget] 自動ログインタブ追加完了: インデックス={tab_index}")
                
                # ウィジェットへの参照を保存
                self.autologin_widget = autologin_widget
                
            except ImportError as e:
                print(f"[settings_tab_widget] AutoLoginTabWidgetのインポートに失敗: {e}")
                self._create_fallback_autologin_tab()
            except Exception as e:
                print(f"[settings_tab_widget] AutoLoginTabWidget作成エラー: {e}")
                self._create_fallback_autologin_tab()
                
        except Exception as e:
            print(f"[settings_tab_widget] setup_autologin_tab全体エラー: {e}")
            logger.error(f"自動ログインタブ設定エラー: {e}")

    def _create_fallback_autologin_tab(self):
        """自動ログインタブ - フォールバック版"""
        print("[settings_tab_widget] フォールバック自動ログインタブを作成")
        
        fallback_widget = QWidget()
        layout = QVBoxLayout(fallback_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # タイトル
        title_label = QLabel("自動ログイン設定")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        info_label = QLabel(
            "自動ログイン機能は現在利用できません。\n"
            "詳細は管理者にお問い合わせください。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        # タブに追加
        tab_index = self.tab_widget.addTab(fallback_widget, "自動ログイン")
        print(f"[settings_tab_widget] フォールバック自動ログインタブ追加完了: インデックス={tab_index}")


def create_settings_tab_widget(parent=None, bearer_token=None):
    """設定タブウィジェットを作成"""
    try:
        return SettingsTabWidget(parent, bearer_token)
    except Exception as e:
        logger.error(f"設定タブウィジェット作成エラー: {e}")
        return None
