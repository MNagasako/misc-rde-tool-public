#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
プロキシ設定ウィジェット v1.17.0
ネットワークプロキシ設定の表示・編集・切り替え機能を提供

主要機能:
- 現在のプロキシ状態表示
- プロキシモード切り替え（DIRECT/SYSTEM/HTTP）
- プリセット設定の適用
- 接続テスト機能
- システムプロキシ自動検出

移行済み: src/widgets → src/classes/config/ui
"""

import os
import sys
import logging
from typing import Dict, Any, Optional

try:
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QComboBox, QLineEdit, QPushButton, QTextEdit,
        QGroupBox, QRadioButton, QButtonGroup, QProgressBar,
        QMessageBox, QFrame, QScrollArea, QCheckBox, QInputDialog
    )
    from PyQt5.QtCore import QTimer, QThread, pyqtSignal, Qt
    from PyQt5.QtGui import QFont, QPalette
    PYQT5_AVAILABLE = True
except ImportError:
    # PyQt5が利用できない場合のフォールバック
    PYQT5_AVAILABLE = False
    
    # ダミークラス
    class QWidget: pass
    class QThread: pass
    def pyqtSignal(*args): return lambda: None

# ログ設定
logger = logging.getLogger(__name__)

class ProxyTestWorker(QThread):
    """プロキシ接続テストのワーカースレッド"""
    test_completed = pyqtSignal(bool, str)  # 成功/失敗, メッセージ
    
    def __init__(self, proxy_config: Dict[str, Any]):
        super().__init__()
        self.proxy_config = proxy_config
        
    def run(self):
        """接続テスト実行"""
        if not PYQT5_AVAILABLE:
            return
            
        try:
            from net.session_manager import ProxySessionManager
            
            # テスト用のセッション管理を作成
            test_manager = ProxySessionManager()
            test_manager.configure(self.proxy_config)
            
            session = test_manager.get_session()
            
            # 接続テスト実行
            response = session.get("https://httpbin.org/ip", timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                ip = data.get('origin', 'unknown')
                self.test_completed.emit(True, f"接続成功! IP: {ip}")
            else:
                self.test_completed.emit(False, f"接続失敗: HTTP {response.status_code}")
                
        except Exception as e:
            self.test_completed.emit(False, f"接続テストエラー: {str(e)}")

class ProxySettingsWidget(QWidget):
    """プロキシ設定ウィジェット"""
    
    def __init__(self, parent=None):
        if not PYQT5_AVAILABLE:
            logger.warning("PyQt5が利用できないため、プロキシ設定ウィジェットを初期化できません")
            super().__init__() if QWidget != type else None
            return
            
        super().__init__(parent)
        self.current_config = {}
        self.test_worker = None
        self.init_ui()
        self.load_current_settings()
        
    def init_ui(self):
        """UI初期化"""
        if not PYQT5_AVAILABLE:
            return
            
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # タイトル
        title_label = QLabel("プロキシ設定")
        title_label.setFont(QFont())  # システム標準フォントを使用
        layout.addWidget(title_label)
        
        # 現在の状態表示
        self.setup_status_section(layout)
        
        # SSL証明書詳細情報
        self.setup_ssl_certificate_details_section(layout)
        
        # 企業CA設定
        self.setup_enterprise_ca_section(layout)
        
        # プロキシモード設定
        self.setup_mode_section(layout)
        
        # プロキシ詳細設定
        self.setup_proxy_details_section(layout)
        
        # プリセット管理
        self.setup_preset_section(layout)
        
        # 接続テスト
        self.setup_test_section(layout)
        
        # 操作ボタン
        self.setup_action_buttons(layout)
        
        # ログ表示
        self.setup_log_section(layout)
        
    def setup_status_section(self, layout):
        """現在の状態表示セクション"""
        status_group = QGroupBox("現在のプロキシ状態")
        status_layout = QGridLayout(status_group)
        
        # 現在のモード
        status_layout.addWidget(QLabel("プロキシモード:"), 0, 0)
        self.current_mode_label = QLabel("読み込み中...")
        self.current_mode_label.setStyleSheet("font-weight: bold; color: blue;")
        status_layout.addWidget(self.current_mode_label, 0, 1)
        
        # 現在のプロキシ
        status_layout.addWidget(QLabel("HTTPプロキシ:"), 1, 0)
        self.current_http_proxy_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_http_proxy_label, 1, 1)
        
        status_layout.addWidget(QLabel("HTTPSプロキシ:"), 2, 0)
        self.current_https_proxy_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_https_proxy_label, 2, 1)
        
        # SSL証明書の状態
        status_layout.addWidget(QLabel("SSL証明書検証:"), 3, 0)
        self.current_ssl_verify_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_ssl_verify_label, 3, 1)
        
        status_layout.addWidget(QLabel("証明書ストア:"), 4, 0)
        self.current_cert_store_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_cert_store_label, 4, 1)
        
        # 検出ボタン
        detect_btn = QPushButton("システムプロキシ検出")
        detect_btn.clicked.connect(self.detect_system_proxy)
        status_layout.addWidget(detect_btn, 5, 0, 1, 2)
        
        layout.addWidget(status_group)
        
    def setup_ssl_certificate_details_section(self, layout):
        """SSL証明書詳細情報セクション"""
        cert_group = QGroupBox("SSL証明書詳細情報")
        cert_layout = QGridLayout(cert_group)
        
        # 証明書バンドルパス
        cert_layout.addWidget(QLabel("証明書バンドルパス:"), 0, 0)
        self.cert_bundle_path_label = QLabel("読み込み中...")
        self.cert_bundle_path_label.setWordWrap(True)
        self.cert_bundle_path_label.setStyleSheet("font-family: monospace; font-size: 10px; color: #666;")
        cert_layout.addWidget(self.cert_bundle_path_label, 0, 1)
        
        # 証明書情報
        cert_layout.addWidget(QLabel("証明書情報:"), 1, 0)
        self.cert_info_label = QLabel("読み込み中...")
        cert_layout.addWidget(self.cert_info_label, 1, 1)
        
        # 使用中の証明書ライブラリ
        cert_layout.addWidget(QLabel("証明書ライブラリ:"), 2, 0)
        self.cert_library_label = QLabel("読み込み中...")
        cert_layout.addWidget(self.cert_library_label, 2, 1)
        
        # SSL戦略詳細
        cert_layout.addWidget(QLabel("SSL処理戦略:"), 3, 0)
        self.ssl_strategy_label = QLabel("読み込み中...")
        cert_layout.addWidget(self.ssl_strategy_label, 3, 1)
        
        # 証明書テストボタン
        cert_test_btn = QPushButton("証明書バンドルを確認")
        cert_test_btn.clicked.connect(self.test_certificate_bundle)
        cert_layout.addWidget(cert_test_btn, 4, 0, 1, 2)
        
        layout.addWidget(cert_group)
        
    def setup_enterprise_ca_section(self, layout):
        """組織内CA設定セクション"""
        enterprise_group = QGroupBox("組織内CA設定 (高度な設定)")
        enterprise_layout = QGridLayout(enterprise_group)
        
        # PAC設定（ラベル）
        pac_section = QLabel("PAC自動設定:")
        pac_section.setStyleSheet("font-weight: bold; color: #2E7D32;")

        # チェックボックスを横並びにするためのコンテナ
        pac_container = QWidget()
        pac_hbox = QHBoxLayout(pac_container)
        pac_hbox.setContentsMargins(0, 0, 0, 0)
        pac_hbox.setSpacing(12)

        self.pac_auto_detect_checkbox = QCheckBox("PAC自動検出")
        self.pac_auto_detect_checkbox.setToolTip("プロキシ自動設定 (PAC) を自動検出")
        pac_hbox.addWidget(self.pac_auto_detect_checkbox)

        self.pac_fallback_checkbox = QCheckBox("PAC失敗時にシステムプロキシにフォールバック")
        self.pac_fallback_checkbox.setToolTip("PAC設定取得に失敗した場合のフォールバック動作")
        pac_hbox.addWidget(self.pac_fallback_checkbox)

        pac_hbox.addStretch()  # 右側余白で左寄せ

        # ★ 同じ行（row=0）に、左: ラベル / 右: チェックボックス群 を配置
        enterprise_layout.addWidget(pac_section,   0, 0, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
        enterprise_layout.addWidget(pac_container, 0, 1, 1, 1)
        
        # 組織内CA証明書（ラベル）
        ca_section = QLabel("組織内CA証明書:")
        ca_section.setStyleSheet("font-weight: bold; color: #2E7D32;")

        # チェックボックスを横並びにするためのコンテナ
        ca_container = QWidget()
        ca_hbox = QHBoxLayout(ca_container)
        ca_hbox.setContentsMargins(0, 0, 0, 0)
        ca_hbox.setSpacing(12)

        self.enable_truststore_checkbox = QCheckBox("truststoreを使用")
        self.enable_truststore_checkbox.setToolTip("truststoreライブラリでシステム証明書を自動取得")
        ca_hbox.addWidget(self.enable_truststore_checkbox)

        self.auto_detect_corporate_ca_checkbox = QCheckBox("組織内CA自動検出")
        self.auto_detect_corporate_ca_checkbox.setToolTip("組織環境のCA証明書を自動検出してバンドルに追加")
        ca_hbox.addWidget(self.auto_detect_corporate_ca_checkbox)

        ca_hbox.addStretch()  # 右側の余白を埋めて左寄せにする

        # ★ 同じ行（row=3）に、左: ラベル / 右: チェックボックス群 を配置
        enterprise_layout.addWidget(ca_section,      3, 0, 1, 1, Qt.AlignRight | Qt.AlignVCenter)
        enterprise_layout.addWidget(ca_container,    3, 1, 1, 1)

        # カスタムCA Bundle 入力欄（存在しないため定義）
        enterprise_layout.addWidget(QLabel("カスタムCA Bundle:"), 4, 0)
        self.custom_ca_bundle_edit = QLineEdit()
        self.custom_ca_bundle_edit.setPlaceholderText("カスタム証明書バンドルファイルのパス")
        enterprise_layout.addWidget(self.custom_ca_bundle_edit, 4, 1)




        # SSL戦略
        ssl_section = QLabel("SSL処理:")
        ssl_section.setStyleSheet("font-weight: bold; color: #2E7D32;")

        enterprise_layout.addWidget(ssl_section, 7, 0)
        self.ssl_strategy_combo = QComboBox()
        self.ssl_strategy_combo.addItems([
            "use_proxy_ca - プロキシCA使用",
            "strict_verification - 厳密検証",
            "fallback_no_verify - フォールバック無検証"
        ])
        enterprise_layout.addWidget(self.ssl_strategy_combo, 7, 1)
        
        # 組織内CA機能テストボタン
        enterprise_test_layout = QHBoxLayout()
        
        test_pac_btn = QPushButton("PAC設定テスト (未実装)")
        test_pac_btn.clicked.connect(self.test_pac_configuration)
        test_pac_btn.setEnabled(False)  # 未実装のため無効化
        enterprise_test_layout.addWidget(test_pac_btn)
        
        test_ca_btn = QPushButton("組織内CA確認")
        test_ca_btn.clicked.connect(self.test_enterprise_ca)
        enterprise_test_layout.addWidget(test_ca_btn)
        
        enterprise_layout.addLayout(enterprise_test_layout, 8, 0, 1, 2)
        
        # 企業CA状況表示
        self.enterprise_ca_status_label = QLabel("組織内CA機能状況: 確認中...")
        self.enterprise_ca_status_label.setStyleSheet("font-size: 10px; color: #666;")
        enterprise_layout.addWidget(self.enterprise_ca_status_label, 9, 0, 1, 2)
        
        layout.addWidget(enterprise_group)
        
        # 企業CA機能状況を初期確認
        self.check_enterprise_ca_features()
        
    def setup_mode_section(self, layout):
        """プロキシモード設定セクション"""
        mode_group = QGroupBox("プロキシモード")
        mode_layout = QVBoxLayout(mode_group)
        
        self.mode_button_group = QButtonGroup(self)
        
        # DIRECT モード
        self.direct_radio = QRadioButton("DIRECT - プロキシを使用しない")
        self.mode_button_group.addButton(self.direct_radio, 0)
        mode_layout.addWidget(self.direct_radio)
        
        # SYSTEM モード
        self.system_radio = QRadioButton("SYSTEM - システムプロキシを自動使用")
        self.mode_button_group.addButton(self.system_radio, 1)
        mode_layout.addWidget(self.system_radio)
        
        # HTTP モード
        self.http_radio = QRadioButton("HTTP - 手動プロキシ設定")
        self.mode_button_group.addButton(self.http_radio, 2)
        mode_layout.addWidget(self.http_radio)
        
        # PAC モード
        self.pac_radio = QRadioButton("PAC - プロキシ自動設定")
        self.mode_button_group.addButton(self.pac_radio, 3)
        mode_layout.addWidget(self.pac_radio)
        
        # モード変更時のイベント
        self.mode_button_group.buttonClicked.connect(self.on_mode_changed)
        
        layout.addWidget(mode_group)
        
    def setup_proxy_details_section(self, layout):
        """プロキシ詳細設定セクション"""
        self.proxy_details_group = QGroupBox("プロキシ詳細設定")
        details_layout = QGridLayout(self.proxy_details_group)
        
        # HTTP プロキシ
        details_layout.addWidget(QLabel("HTTPプロキシ:"), 0, 0)
        self.http_proxy_edit = QLineEdit()
        self.http_proxy_edit.setPlaceholderText("http://proxy.example.com:8080")
        details_layout.addWidget(self.http_proxy_edit, 0, 1)
        
        # HTTPS プロキシ
        details_layout.addWidget(QLabel("HTTPSプロキシ:"), 1, 0)
        self.https_proxy_edit = QLineEdit()
        self.https_proxy_edit.setPlaceholderText("http://proxy.example.com:8080")
        details_layout.addWidget(self.https_proxy_edit, 1, 1)
        
        # 除外リスト
        details_layout.addWidget(QLabel("除外リスト:"), 2, 0)
        self.no_proxy_edit = QLineEdit()
        self.no_proxy_edit.setPlaceholderText("localhost,127.0.0.1,.local")
        details_layout.addWidget(self.no_proxy_edit, 2, 1)
        
        # HTTPSプロキシ同期チェックボックス
        self.sync_https_checkbox = QCheckBox("HTTPSプロキシをHTTPプロキシと同じにする")
        self.sync_https_checkbox.setChecked(True)
        self.sync_https_checkbox.toggled.connect(self.on_sync_https_toggled)
        details_layout.addWidget(self.sync_https_checkbox, 3, 0, 1, 2)
        
        # 入力変更時のイベント
        self.http_proxy_edit.textChanged.connect(self.on_proxy_details_changed)
        
        layout.addWidget(self.proxy_details_group)
        
    def setup_preset_section(self, layout):
        """プリセット管理セクション"""
        preset_group = QGroupBox("プリセット設定")
        preset_layout = QHBoxLayout(preset_group)
        
        preset_layout.addWidget(QLabel("プリセット:"))
        
        self.preset_combo = QComboBox()
        preset_layout.addWidget(self.preset_combo)
        
        apply_preset_btn = QPushButton("適用")
        apply_preset_btn.clicked.connect(self.apply_preset)
        preset_layout.addWidget(apply_preset_btn)
        
        save_preset_btn = QPushButton("現在設定を保存 (未実装)")
        save_preset_btn.clicked.connect(self.save_current_as_preset)
        save_preset_btn.setEnabled(False)  # 未実装のため無効化
        preset_layout.addWidget(save_preset_btn)
        
        layout.addWidget(preset_group)
        
    def setup_test_section(self, layout):
        """接続テストセクション"""
        test_group = QGroupBox("接続テスト")
        test_layout = QVBoxLayout(test_group)
        
        test_btn_layout = QHBoxLayout()
        
        self.test_button = QPushButton("接続テスト実行")
        self.test_button.clicked.connect(self.run_connection_test)
        test_btn_layout.addWidget(self.test_button)
        
        self.test_progress = QProgressBar()
        self.test_progress.setVisible(False)
        test_btn_layout.addWidget(self.test_progress)
        
        test_layout.addLayout(test_btn_layout)
        
        self.test_result_label = QLabel("テスト実行前")
        test_layout.addWidget(self.test_result_label)
        
        layout.addWidget(test_group)
        
    def setup_action_buttons(self, layout):
        """操作ボタンセクション"""
        button_layout = QHBoxLayout()
        
        apply_btn = QPushButton("設定を適用")
        apply_btn.clicked.connect(self.apply_settings)
        apply_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        button_layout.addWidget(apply_btn)
        
        reload_btn = QPushButton("設定を再読み込み")
        reload_btn.clicked.connect(self.load_current_settings)
        button_layout.addWidget(reload_btn)
        
        reset_btn = QPushButton("デフォルトに戻す (未実装)")
        reset_btn.clicked.connect(self.reset_to_defaults)
        reset_btn.setEnabled(False)  # 未実装のため無効化
        button_layout.addWidget(reset_btn)
        
        layout.addLayout(button_layout)
        
    def setup_log_section(self, layout):
        """ログ表示セクション"""
        log_group = QGroupBox("ログ")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(150)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        clear_log_btn = QPushButton("ログクリア")
        clear_log_btn.clicked.connect(self.clear_log)
        log_layout.addWidget(clear_log_btn)
        
        layout.addWidget(log_group)
        
    def load_current_settings(self):
        """現在の設定を読み込み"""
        try:
            from net.session_manager import ProxySessionManager
            
            manager = ProxySessionManager()
            self.current_config = manager.get_proxy_config()
            
            if not self.current_config:
                # 設定ファイルから直接読み込み
                manager.configure()
                self.current_config = manager.get_proxy_config()
            
            self.update_ui_from_config()
            self.load_presets()
            self.add_log("設定を読み込みました")
            
        except Exception as e:
            self.add_log(f"設定読み込みエラー: {e}")
            logger.error(f"設定読み込みエラー: {e}")
            
    def load_presets(self):
        """プリセット一覧を読み込み"""
        try:
            from config.common import get_dynamic_file_path
            import yaml
            
            yaml_path = get_dynamic_file_path("config/network.yaml")
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    
                configurations = data.get('configurations', {})
                
                self.preset_combo.clear()
                self.preset_combo.addItem("-- プリセット選択 --", None)
                
                for name, config in configurations.items():
                    mode = config.get('mode', 'UNKNOWN')
                    display_name = f"{name} ({mode})"
                    self.preset_combo.addItem(display_name, name)
                    
        except Exception as e:
            self.add_log(f"プリセット読み込みエラー: {e}")
            
    def update_ssl_certificate_status(self):
        """SSL証明書の使用状況を更新"""
        try:
            cert_config = self.current_config.get('cert', {})
            
            # SSL検証状態
            ssl_verify = cert_config.get('verify', True)
            if ssl_verify:
                verify_text = "有効"
                verify_style = "color: green; font-weight: bold;"
            else:
                verify_text = "無効"
                verify_style = "color: red; font-weight: bold;"
            
            self.current_ssl_verify_label.setText(verify_text)
            self.current_ssl_verify_label.setStyleSheet(verify_style)
            
            # 証明書ストア情報
            use_os_store = cert_config.get('use_os_store', False)
            ca_bundle = cert_config.get('ca_bundle', '')
            proxy_ssl_handling = cert_config.get('proxy_ssl_handling', {})
            ssl_strategy = proxy_ssl_handling.get('strategy', 'default')
            
            # 証明書ストアの詳細表示
            cert_store_parts = []
            
            if ssl_verify:
                if ca_bundle:
                    cert_store_parts.append(f"カスタムCA: {os.path.basename(ca_bundle)}")
                elif use_os_store:
                    cert_store_parts.append("OSストア")
                else:
                    # certifi等のデフォルト
                    try:
                        import certifi
                        cert_store_parts.append("certifi")
                    except ImportError:
                        cert_store_parts.append("デフォルト")
                
                # プロキシ環境での戦略も表示
                if ssl_strategy != 'default':
                    strategy_names = {
                        'disable_verify': '検証無効',
                        'use_proxy_ca': 'プロキシCA',
                        'ignore_proxy': 'プロキシ無視'
                    }
                    strategy_display = strategy_names.get(ssl_strategy, ssl_strategy)
                    cert_store_parts.append(f"戦略:{strategy_display}")
            else:
                cert_store_parts.append("検証無効のため未使用")
            
            cert_store_text = " | ".join(cert_store_parts) if cert_store_parts else "不明"
            
            # プロキシ環境かどうかの判定
            mode = self.current_config.get('mode', 'DIRECT').upper()
            if mode == 'SYSTEM':
                from urllib.request import getproxies
                system_proxies = getproxies()
                is_proxy_env = bool(system_proxies.get('http') or system_proxies.get('https'))
            else:
                proxies_config = self.current_config.get('proxies', {})
                is_proxy_env = bool(proxies_config.get('http') or proxies_config.get('https'))
            
            if is_proxy_env:
                cert_store_text = f"🔗 プロキシ環境: {cert_store_text}"
            else:
                cert_store_text = f"📡 直接接続: {cert_store_text}"
            
            self.current_cert_store_label.setText(cert_store_text)
            
            # プロキシ環境でSSL有効の場合は警告表示
            if is_proxy_env and ssl_verify:
                self.current_cert_store_label.setStyleSheet("color: orange; font-size: 11px;")
                self.current_cert_store_label.setToolTip("プロキシ環境でSSL検証が有効です。接続問題が発生する可能性があります。")
            else:
                self.current_cert_store_label.setStyleSheet("color: black; font-size: 11px;")
                self.current_cert_store_label.setToolTip("")
                
        except Exception as e:
            self.current_ssl_verify_label.setText("取得エラー")
            self.current_cert_store_label.setText(f"エラー: {e}")
            logger.error(f"SSL証明書状態更新エラー: {e}")
    
    def update_ssl_certificate_details(self):
        """SSL証明書詳細情報を更新"""
        try:
            cert_config = self.current_config.get('cert', {})
            ssl_verify = cert_config.get('verify', True)
            
            # 実際に使用される証明書バンドルパスを取得
            from net.session_manager import ProxySessionManager
            manager = ProxySessionManager()
            session = manager.get_session()
            
            cert_bundle_path = "不明"
            cert_info = "情報取得中..."
            cert_library = "不明"
            ssl_strategy_info = "不明"
            
            # 使用中の証明書バンドル情報
            if ssl_verify:
                if hasattr(session, 'verify') and session.verify:
                    if isinstance(session.verify, str):
                        # カスタム証明書ファイル
                        cert_bundle_path = session.verify
                        if os.path.exists(cert_bundle_path):
                            file_size = os.path.getsize(cert_bundle_path)
                            import datetime
                            mtime = os.path.getmtime(cert_bundle_path)
                            mtime_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                            cert_info = f"サイズ: {file_size:,} bytes | 更新日: {mtime_str}"
                        else:
                            cert_info = "ファイルが存在しません"
                    else:
                        # デフォルト証明書
                        try:
                            import certifi
                            cert_bundle_path = certifi.where()
                            file_size = os.path.getsize(cert_bundle_path)
                            import datetime
                            mtime = os.path.getmtime(cert_bundle_path)
                            mtime_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                            
                            # certifiのバージョンも取得
                            import certifi
                            certifi_version = getattr(certifi, '__version__', 'Unknown')
                            
                            cert_info = f"サイズ: {file_size:,} bytes | 更新日: {mtime_str}"
                            cert_library = f"certifi v{certifi_version}"
                        except ImportError:
                            cert_bundle_path = "システムデフォルト"
                            cert_info = "certifi利用不可"
                            cert_library = "システム標準"
                        except Exception as e:
                            cert_info = f"取得エラー: {e}"
                else:
                    cert_bundle_path = "検証無効"
                    cert_info = "SSL検証が無効のため使用されません"
                    cert_library = "未使用"
            else:
                cert_bundle_path = "検証無効"
                cert_info = "SSL検証が無効のため使用されません"
                cert_library = "未使用"
            
            # SSL戦略情報
            proxy_ssl_handling = cert_config.get('proxy_ssl_handling', {})
            strategy = proxy_ssl_handling.get('strategy', 'default')
            fallback = proxy_ssl_handling.get('fallback_to_no_verify', False)
            log_errors = proxy_ssl_handling.get('log_ssl_errors', True)
            
            strategy_details = {
                'disable_verify': 'SSL検証を完全無効化',
                'use_proxy_ca': 'プロキシ証明書処理 + フォールバック',
                'ignore_proxy': 'プロキシを無視してSSL設定適用',
                'default': 'デフォルト戦略'
            }
            
            strategy_name = strategy_details.get(strategy, strategy)
            if fallback:
                strategy_name += " (フォールバック有効)"
            
            ssl_strategy_info = strategy_name
            
            # UI更新
            self.cert_bundle_path_label.setText(cert_bundle_path)
            self.cert_info_label.setText(cert_info)
            self.cert_library_label.setText(cert_library)
            self.ssl_strategy_label.setText(ssl_strategy_info)
            
        except Exception as e:
            self.cert_bundle_path_label.setText(f"エラー: {e}")
            self.cert_info_label.setText("取得失敗")
            self.cert_library_label.setText("取得失敗")
            self.ssl_strategy_label.setText("取得失敗")
            logger.error(f"SSL証明書詳細更新エラー: {e}")
    
    def test_certificate_bundle(self):
        """証明書バンドルのテスト"""
        try:
            from net.session_manager import ProxySessionManager
            manager = ProxySessionManager()
            session = manager.get_session()
            
            if hasattr(session, 'verify') and session.verify:
                if isinstance(session.verify, str) and os.path.exists(session.verify):
                    # 証明書ファイルの内容確認
                    with open(session.verify, 'r', encoding='utf-8') as f:
                        content = f.read()
                        cert_count = content.count('BEGIN CERTIFICATE')
                        
                    QMessageBox.information(self, "証明書バンドル情報",
                                          f"証明書ファイル: {session.verify}\n"
                                          f"証明書数: {cert_count}件\n"
                                          f"ファイルサイズ: {len(content):,} 文字")
                else:
                    QMessageBox.information(self, "証明書バンドル情報",
                                          f"証明書設定: {session.verify}\n"
                                          "（システムデフォルト証明書を使用）")
            else:
                QMessageBox.warning(self, "証明書バンドル情報",
                                  "SSL証明書検証が無効のため、証明書バンドルは使用されていません")
                
        except Exception as e:
            QMessageBox.warning(self, "エラー", f"証明書バンドル情報取得エラー: {e}")
            
    def on_mode_changed(self):
        """プロキシモード変更時の処理"""
        if self.http_radio.isChecked():
            self.proxy_details_group.setEnabled(True)
        else:
            self.proxy_details_group.setEnabled(False)
            
        # PAC設定についてのヒント表示
        if hasattr(self, 'pac_radio') and self.pac_radio.isChecked():
            self.add_log("PAC自動設定モードを選択しました。組織内CA設定セクションでPAC自動検出を有効化してください。")
            
    def on_sync_https_toggled(self):
        """HTTPS同期チェックボックス変更時の処理"""
        if self.sync_https_checkbox.isChecked():
            self.https_proxy_edit.setEnabled(False)
            self.https_proxy_edit.setText(self.http_proxy_edit.text())
        else:
            self.https_proxy_edit.setEnabled(True)
            
    def on_proxy_details_changed(self):
        """プロキシ詳細変更時の処理"""
        if self.sync_https_checkbox.isChecked():
            self.https_proxy_edit.setText(self.http_proxy_edit.text())
            
    def detect_system_proxy(self):
        """システムプロキシ検出"""
        try:
            from net.session_manager import ProxySessionManager
            
            manager = ProxySessionManager()
            proxy_info = manager.get_system_proxy_info()
            
            if proxy_info.get('detected', False):
                proxies = proxy_info.get('proxies', {})
                self.add_log(f"システムプロキシ検出: {proxies}")
                
                # 検出されたプロキシを入力欄に設定
                http_proxy = proxies.get('http', '')
                https_proxy = proxies.get('https', '')
                
                if http_proxy:
                    self.http_proxy_edit.setText(http_proxy)
                if https_proxy:
                    self.https_proxy_edit.setText(https_proxy)
                    
                QMessageBox.information(self, "システムプロキシ検出",
                                      f"システムプロキシを検出しました:\nHTTP: {http_proxy}\nHTTPS: {https_proxy}")
            else:
                self.add_log("システムプロキシが検出されませんでした")
                QMessageBox.information(self, "システムプロキシ検出",
                                      "システムプロキシが検出されませんでした")
                
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_error_message(f"システムプロキシ検出エラー: {error_msg}", max_line_length=80)
            
            self.add_log(formatted_error)
            QMessageBox.warning(self, "エラー", formatted_error)
            
    def apply_preset(self):
        """プリセット適用"""
        preset_name = self.preset_combo.currentData()
        if not preset_name:
            return
            
        try:
            from config.common import get_dynamic_file_path
            import yaml
            
            yaml_path = get_dynamic_file_path("config/network.yaml")
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    
                configurations = data.get('configurations', {})
                preset_config = configurations.get(preset_name, {})
                
                # プリセット設定をUIに適用
                mode = preset_config.get('mode', 'DIRECT').upper()
                
                if mode == 'DIRECT':
                    self.direct_radio.setChecked(True)
                elif mode == 'SYSTEM':
                    self.system_radio.setChecked(True)
                elif mode == 'HTTP':
                    self.http_radio.setChecked(True)
                    
                self.http_proxy_edit.setText(preset_config.get('http_proxy', ''))
                self.https_proxy_edit.setText(preset_config.get('https_proxy', ''))
                
                self.on_mode_changed()
                self.add_log(f"プリセット '{preset_name}' を適用しました")
                
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_error_message(f"プリセット適用エラー: {error_msg}", max_line_length=80)
            
            self.add_log(formatted_error)
            QMessageBox.warning(self, "エラー", formatted_error)
            
    def save_current_as_preset(self):
        """現在の設定をプリセットとして保存"""
        from PyQt5.QtWidgets import QInputDialog
        
        preset_name, ok = QInputDialog.getText(self, "プリセット保存", "プリセット名を入力してください:")
        
        if ok and preset_name:
            try:
                config = self.get_current_ui_config()
                
                from config.common import get_dynamic_file_path
                import yaml
                
                yaml_path = get_dynamic_file_path("config/network.yaml")
                data = {}
                
                if os.path.exists(yaml_path):
                    with open(yaml_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f) or {}
                
                if 'configurations' not in data:
                    data['configurations'] = {}
                    
                data['configurations'][preset_name] = config
                
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(data, f, default_flow_style=False, 
                                 allow_unicode=True, sort_keys=False)
                
                self.load_presets()  # プリセット一覧を再読み込み
                self.add_log(f"プリセット '{preset_name}' を保存しました")
                QMessageBox.information(self, "保存完了", f"プリセット '{preset_name}' を保存しました")
                
            except Exception as e:
                error_msg = str(e)
                formatted_error = self._format_error_message(f"プリセット保存エラー: {error_msg}", max_line_length=80)
                
                self.add_log(formatted_error)
                QMessageBox.warning(self, "エラー", formatted_error)
                
    def run_connection_test(self):
        """接続テスト実行"""
        if self.test_worker and self.test_worker.isRunning():
            return
            
        config = self.get_current_ui_config()
        
        self.test_button.setEnabled(False)
        self.test_progress.setVisible(True)
        self.test_progress.setRange(0, 0)  # 不定期間プログレスバー
        self.test_result_label.setText("接続テスト実行中...")
        
        self.test_worker = ProxyTestWorker(config)
        self.test_worker.test_completed.connect(self.on_test_completed)
        self.test_worker.start()
        
        self.add_log("接続テストを開始しました")
        
    def _format_error_message(self, message: str, max_line_length: int = 80) -> str:
        """
        エラーメッセージを適切な長さで改行する
        
        Args:
            message: 元のメッセージ
            max_line_length: 1行の最大文字数
            
        Returns:
            str: 改行されたメッセージ
        """
        if len(message) <= max_line_length:
            return message
        
        # 長いメッセージを単語境界で改行
        words = message.split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            # 現在の行に単語を追加した場合の長さを確認
            test_line = current_line + (" " if current_line else "") + word
            
            if len(test_line) <= max_line_length:
                current_line = test_line
            else:
                # 現在の行が空でない場合は保存
                if current_line:
                    lines.append(current_line)
                
                # 単語が最大長より長い場合は強制的に分割
                if len(word) > max_line_length:
                    while len(word) > max_line_length:
                        lines.append(word[:max_line_length])
                        word = word[max_line_length:]
                    current_line = word if word else ""
                else:
                    current_line = word
        
        # 最後の行を追加
        if current_line:
            lines.append(current_line)
        
        return '\n'.join(lines)
    
    def on_test_completed(self, success: bool, message: str):
        """接続テスト完了時の処理"""
        self.test_button.setEnabled(True)
        self.test_progress.setVisible(False)
        
        # エラーメッセージを適切な長さで改行
        formatted_message = self._format_error_message(message, max_line_length=100)
        
        if success:
            self.test_result_label.setText(f"✅ {formatted_message}")
            self.test_result_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.test_result_label.setText(f"❌ {formatted_message}")
            self.test_result_label.setStyleSheet("color: red; font-weight: bold;")
        
        # ラベルでの改行表示を有効化
        self.test_result_label.setWordWrap(True)
        
        # ログにも改行されたメッセージを記録
        self.add_log(f"接続テスト完了: {formatted_message}")
        
    def check_enterprise_ca_features(self):
        """組織内CA機能の利用可否確認"""
        try:
            features = []
            
            # pypac確認
            try:
                import pypac
                features.append("PAC自動設定")
            except ImportError:
                pass
                
            # truststore確認
            try:
                import truststore
                features.append("truststore")
            except ImportError:
                pass
                
            # wincertstore確認
            try:
                import wincertstore
                features.append("Windows証明書ストア")
            except ImportError:
                pass
                
            if features:
                status = f"利用可能機能: {', '.join(features)}"
                self.enterprise_ca_status_label.setStyleSheet("color: green; font-size: 10px;")
            else:
                status = "組織内CA機能は利用できません (パッケージ未インストール)"
                self.enterprise_ca_status_label.setStyleSheet("color: orange; font-size: 10px;")
                
            self.enterprise_ca_status_label.setText(status)
            
        except Exception as e:
            self.enterprise_ca_status_label.setText(f"機能確認エラー: {e}")
            self.enterprise_ca_status_label.setStyleSheet("color: red; font-size: 10px;")
            
    def test_pac_configuration(self):
        """PAC設定テスト"""
        try:
            import pypac
            
            self.add_log("PAC自動検出を開始...")
            
            # PAC検出
            pac = pypac.get_pac()
            if pac:
                self.add_log(f"✅ PAC検出成功: {pac}")
                
                # テスト用URLでプロキシ確認
                test_url = "https://www.google.com"
                proxy = pac.find_proxy_for_url(test_url, "www.google.com")
                self.add_log(f"テストURL ({test_url}) のプロキシ: {proxy}")
                
                QMessageBox.information(self, "PAC設定テスト", 
                                      f"PAC検出成功!\n\nPAC: {pac}\nテストプロキシ: {proxy}")
            else:
                self.add_log("⚠️ PAC検出失敗")
                QMessageBox.warning(self, "PAC設定テスト", 
                                  "PAC自動検出に失敗しました")
                
        except ImportError:
            QMessageBox.warning(self, "PAC設定テスト", 
                              "pypacパッケージがインストールされていません")
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_error_message(error_msg, max_line_length=80)
            
            self.add_log(f"❌ PAC設定テストエラー: {formatted_error}")
            QMessageBox.critical(self, "PAC設定テスト", 
                               f"PAC設定テストでエラーが発生しました:\n\n{formatted_error}")
            
    def test_enterprise_ca(self):
        """組織内CA確認テスト"""
        try:
            info_lines = []
            
            # certifi標準バンドル
            try:
                import certifi
                standard_bundle = certifi.where()
                standard_size = os.path.getsize(standard_bundle)
                info_lines.append(f"標準certifiバンドル:")
                info_lines.append(f"  パス: {standard_bundle}")
                info_lines.append(f"  サイズ: {standard_size:,} bytes")
            except Exception as e:
                info_lines.append(f"標準certifiバンドル: エラー - {e}")
                
            # truststore証明書バンドル
            try:
                import truststore
                info_lines.append(f"truststore:")
                info_lines.append(f"  バージョン: {truststore.__version__}")
                info_lines.append(f"  SSL強化: 利用可能")
            except ImportError:
                info_lines.append("truststore: 利用不可 (truststore未インストール)")
            except Exception as e:
                info_lines.append(f"truststore: エラー - {e}")
                
            # Windows証明書ストア
            try:
                import wincertstore
                ca_store = wincertstore.CertSystemStore('CA')
                root_store = wincertstore.CertSystemStore('ROOT')
                
                ca_count = len(list(ca_store.itercerts()))
                root_count = len(list(root_store.itercerts()))
                
                info_lines.append(f"Windows証明書ストア:")
                info_lines.append(f"  CA証明書: {ca_count}件")
                info_lines.append(f"  ROOT証明書: {root_count}件")
            except ImportError:
                info_lines.append("Windows証明書ストア: 利用不可 (wincertstore未インストール)")
            except Exception as e:
                info_lines.append(f"Windows証明書ストア: エラー - {e}")
                
            # 現在のセッションマネージャ設定
            try:
                from net.session_manager import ProxySessionManager
                manager = ProxySessionManager()
                current_verify = getattr(manager.get_session(), 'verify', 'なし')
                info_lines.append(f"現在のSSL検証設定: {current_verify}")
            except Exception as e:
                info_lines.append(f"現在のセッション情報: エラー - {e}")
                
            info_text = "\n".join(info_lines)
            
            # ログにも出力
            for line in info_lines:
                self.add_log(line)
                
            QMessageBox.information(self, "組織内CA確認", 
                                  f"組織内CA情報:\n\n{info_text}")
            
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_error_message(error_msg, max_line_length=80)
            
            full_error_msg = f"組織内CA確認でエラーが発生しました:\n\n{formatted_error}"
            self.add_log(f"❌ 組織内CA確認エラー: {formatted_error}")
            QMessageBox.critical(self, "組織内CA確認", full_error_msg)
            
    def update_ui_from_config(self):
        """設定からUIを更新 (企業CA設定含む) - ファイル読み込み時やプリセット適用時に使用"""
        mode = self.current_config.get('mode', 'DIRECT').upper()
        
        # ログ出力で呼び出し元を明確化
        self.add_log(f"🔄 UI更新開始 - 設定ファイルからUI入力欄を更新: {mode}")
        
        # 現在の状態表示を更新
        self.current_mode_label.setText(mode)
        
        # プロキシ情報表示
        if mode == 'SYSTEM':
            try:
                from urllib.request import getproxies
                system_proxies = getproxies()
                http_proxy = system_proxies.get('http', 'なし')
                https_proxy = system_proxies.get('https', 'なし')
            except:
                http_proxy = 'システム設定取得エラー'
                https_proxy = 'システム設定取得エラー'
        else:
            proxies_config = self.current_config.get('proxies', {})
            http_proxy = (self.current_config.get('http_proxy') or 
                         proxies_config.get('http', 'なし'))
            https_proxy = (self.current_config.get('https_proxy') or 
                          proxies_config.get('https', 'なし'))
        
        self.current_http_proxy_label.setText(http_proxy)
        self.current_https_proxy_label.setText(https_proxy)
        
        # SSL証明書状態を更新
        self.update_ssl_certificate_status()
        self.update_ssl_certificate_details()
        
        # モードラジオボタン設定
        if mode == 'DIRECT':
            self.direct_radio.setChecked(True)
        elif mode == 'SYSTEM':
            self.system_radio.setChecked(True)
        elif mode == 'HTTP':
            self.http_radio.setChecked(True)
        elif mode == 'PAC':
            self.pac_radio.setChecked(True)
            
        # プロキシ詳細設定
        self.http_proxy_edit.setText(self.current_config.get('http_proxy', ''))
        self.https_proxy_edit.setText(self.current_config.get('https_proxy', ''))
        self.no_proxy_edit.setText(self.current_config.get('no_proxy', ''))
        
        # 企業CA設定の更新
        self.update_enterprise_ca_ui()
        
        # 除外リスト
        no_proxy = self.current_config.get('no_proxy', '')
        self.no_proxy_edit.setText(no_proxy)
        
        self.on_mode_changed()
        
    def update_enterprise_ca_ui(self):
        """企業CA設定UIの更新"""
        try:
            cert_config = self.current_config.get('cert', {})
            enterprise_ca = cert_config.get('enterprise_ca', {})
            pac_config = self.current_config.get('pac', {})
            
            # PAC設定
            self.pac_auto_detect_checkbox.setChecked(pac_config.get('auto_detect', False))
            self.pac_fallback_checkbox.setChecked(pac_config.get('fallback_to_system', True))
            
            # 企業CA設定
            self.enable_truststore_checkbox.setChecked(enterprise_ca.get('enable_truststore', False))
            self.auto_detect_corporate_ca_checkbox.setChecked(enterprise_ca.get('auto_detect_corporate_ca', False))
            self.custom_ca_bundle_edit.setText(enterprise_ca.get('custom_ca_bundle', ''))
            
            # SSL戦略設定
            proxy_ssl = cert_config.get('proxy_ssl_handling', {})
            strategy = proxy_ssl.get('strategy', 'use_proxy_ca')
            
            strategy_index = 0
            if strategy == 'strict_verification':
                strategy_index = 1
            elif strategy == 'fallback_no_verify':
                strategy_index = 2
                
            self.ssl_strategy_combo.setCurrentIndex(strategy_index)
            
        except Exception as e:
            self.add_log(f"企業CA UI更新エラー: {e}")
            
    def update_current_status_display(self):
        """現在の状態表示のみを更新（入力フィールドは変更しない）"""
        try:
            mode = self.current_config.get('mode', 'DIRECT').upper()
            
            # 現在の状態表示を更新
            self.current_mode_label.setText(mode)
            
            # プロキシ情報表示
            if mode == 'SYSTEM':
                try:
                    from urllib.request import getproxies
                    system_proxies = getproxies()
                    http_proxy = system_proxies.get('http', 'なし')
                    https_proxy = system_proxies.get('https', 'なし')
                except:
                    http_proxy = 'システム設定取得エラー'
                    https_proxy = 'システム設定取得エラー'
            else:
                proxies_config = self.current_config.get('proxies', {})
                http_proxy = (self.current_config.get('http_proxy') or 
                             proxies_config.get('http', 'なし'))
                https_proxy = (self.current_config.get('https_proxy') or 
                              proxies_config.get('https', 'なし'))
            
            self.current_http_proxy_label.setText(http_proxy)
            self.current_https_proxy_label.setText(https_proxy)
            
            # SSL証明書状態を更新
            self.update_ssl_certificate_status()
            self.update_ssl_certificate_details()
            
        except Exception as e:
            self.add_log(f"状態表示更新エラー: {e}")
            
    def get_current_ui_config(self):
        """現在のUI設定から設定辞書を取得 (企業CA設定含む)"""
        config = {}
        
        # 基本プロキシ設定
        if self.direct_radio.isChecked():
            config['mode'] = 'DIRECT'
        elif self.system_radio.isChecked():
            config['mode'] = 'SYSTEM'
        elif self.http_radio.isChecked():
            config['mode'] = 'HTTP'
            config['http_proxy'] = self.http_proxy_edit.text()
            config['https_proxy'] = self.https_proxy_edit.text()
        elif self.pac_radio.isChecked():
            config['mode'] = 'PAC'
            
        config['no_proxy'] = self.no_proxy_edit.text()
        
        # 企業CA設定の追加
        if hasattr(self, 'pac_auto_detect_checkbox'):
            config['pac'] = {
                'auto_detect': self.pac_auto_detect_checkbox.isChecked(),
                'fallback_to_system': self.pac_fallback_checkbox.isChecked(),
                'timeout': 10
            }
            
            # SSL戦略
            strategy_map = {
                0: 'use_proxy_ca',
                1: 'strict_verification', 
                2: 'fallback_no_verify'
            }
            
            config['cert'] = {
                'verify': True,
                'enterprise_ca': {
                    'enable_truststore': self.enable_truststore_checkbox.isChecked(),
                    'auto_detect_corporate_ca': self.auto_detect_corporate_ca_checkbox.isChecked(),
                    'custom_ca_bundle': self.custom_ca_bundle_edit.text()
                },
                'proxy_ssl_handling': {
                    'strategy': strategy_map.get(self.ssl_strategy_combo.currentIndex(), 'use_proxy_ca'),
                    'fallback_to_no_verify': True,
                    'log_ssl_errors': True
                }
            }
            
        return config
        
    def apply_settings(self):
        """設定を適用"""
        try:
            config = self.get_current_ui_config()
            
            # デバッグ：適用しようとしている設定をログに出力
            mode = config.get('mode', 'UNKNOWN')
            self.add_log(f"🔧 設定適用開始 - モード: {mode}")
            
            if mode == 'HTTP':
                http_proxy = config.get('http_proxy', '')
                https_proxy = config.get('https_proxy', '')
                self.add_log(f"📋 手動プロキシ設定:")
                self.add_log(f"   HTTP: {http_proxy}")
                self.add_log(f"   HTTPS: {https_proxy}")
            
            from net.session_manager import ProxySessionManager
            manager = ProxySessionManager()
            manager.configure(config)
            
            # 設定ファイルにも保存
            from config.common import get_dynamic_file_path
            import yaml
            
            yaml_path = get_dynamic_file_path("config/network.yaml")
            data = {}
            
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
            
            # メイン設定を更新
            data['mode'] = config.get('mode', 'DIRECT')
            if 'http_proxy' in config:
                data['http_proxy'] = config['http_proxy']
                self.add_log(f"💾 ファイル保存 - HTTP: {config['http_proxy']}")
            if 'https_proxy' in config:
                data['https_proxy'] = config['https_proxy']
                self.add_log(f"💾 ファイル保存 - HTTPS: {config['https_proxy']}")
                
            with open(yaml_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, default_flow_style=False, 
                             allow_unicode=True, sort_keys=False)
            
            # 現在の設定を保存済みの設定で更新（UIは保持）
            self.current_config = config.copy()
            
            # 現在の状態表示のみを更新（入力フィールドは変更しない）
            self.update_current_status_display()
            
            self.add_log("✅ 設定を適用しました")
            QMessageBox.information(self, "設定適用", "プロキシ設定を適用しました")
            
        except Exception as e:
            error_msg = str(e)
            formatted_error = self._format_error_message(f"設定適用エラー: {error_msg}", max_line_length=80)
            
            self.add_log(formatted_error)
            QMessageBox.warning(self, "エラー", formatted_error)
            
    def reset_to_defaults(self):
        """デフォルト設定に戻す"""
        reply = QMessageBox.question(self, "デフォルトに戻す",
                                   "プロキシ設定をデフォルト（DIRECT）に戻しますか？",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            self.direct_radio.setChecked(True)
            self.http_proxy_edit.clear()
            self.https_proxy_edit.clear()
            self.no_proxy_edit.setText("localhost,127.0.0.1,.local")
            self.on_mode_changed()
            self.add_log("設定をデフォルトに戻しました")
            
    def clear_log(self):
        """ログクリア"""
        self.log_text.clear()
        
    def add_log(self, message: str):
        """ログメッセージ追加"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
        # 自動スクロール
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
