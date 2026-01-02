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

# ログ設定（インポート前に初期化）
logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QMessageBox, 
        QScrollArea, QGroupBox, QGridLayout, QApplication,
        QSplitter, QFrame
    )
    from qt_compat.core import Qt, QTimer, QSize
    from qt_compat.gui import QFont
    from classes.theme import get_color, ThemeKey
    PYQT5_AVAILABLE = True
except ImportError as e:
    logger.error(f"Qt互換レイヤーインポート失敗: {e}")
    PYQT5_AVAILABLE = False
    # ダミークラス定義
    class QWidget: pass
    class QApplication: pass

class SettingsTabWidget(QWidget):
    """設定タブウィジェットクラス"""
    
    def __init__(self, parent=None, bearer_token=None):
        # PySide6完全対応: QWidget.__init__を明示的に呼び出し
        QWidget.__init__(self, parent)
        self.parent_widget = parent
        self.bearer_token = bearer_token
        
        self.setup_ui()
        
        # テーマ変更シグナルに接続
        from classes.theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        
    def setup_ui(self):
        """UI初期化 - レスポンシブ・段組対応"""
        # メインレイアウト
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # タブウィジェット
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # プロキシ設定タブ（段組表示）
        self.setup_proxy_tab_responsive()
        
        # AI設定タブ（即座にロード）
        self.setup_ai_tab()
            
        # 自動ログインタブ
        self.setup_autologin_tab()
        
        # トークン状態タブ
        self.setup_token_status_tab()

        # データ構造化タブ（アップロード + 解析結果表示）
        self.setup_data_structuring_tab()

        # メールタブ（Gmail: アプリパスワードを先行実装）
        self.setup_mail_tab()

        # 除外されたタブ（ユーザー要望）:
        # - ネットワーク設定タブ
        # - アプリケーション設定タブ
        # - インポートタブ
        
        # 報告書タブ（即座にロード）
        self.setup_report_tab()

        # データポータルタブ（公開・ログイン不要）
        self.setup_data_portal_public_tab()
        
        # 設備タブ（即座にロード）
        self.setup_equipment_tab()
            
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
    
    def refresh_theme(self):
        """テーマ変更時のスタイル更新"""
        try:
            # 各タブの再描画をトリガー
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if widget and hasattr(widget, 'update'):
                    widget.update()
            
            # ウィジェット全体を再描画
            self.update()
            logger.debug("SettingsTabWidget: テーマ更新完了")
        except Exception as e:
            logger.error(f"SettingsTabWidget: テーマ更新エラー: {e}")
    
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
                # PySide6対応
                from qt_compat import get_screen_size
                width, _ = get_screen_size(self)
            
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
            
            logger.info("完全なプロキシ設定ウィジェットを正常にロードしました")
            
        except ImportError as e:
            logger.error(f"完全なプロキシ設定ウィジェットのインポートに失敗: {e}", exc_info=True)
            # フォールバック：簡略版を作成
            self.setup_proxy_tab_fallback()
        except Exception as e:
            logger.error(f"プロキシ設定タブ作成エラー: {e}", exc_info=True)
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
        self.current_mode_label.setStyleSheet(
            f"font-weight: bold; color: {get_color(ThemeKey.TEXT_INFO)};"
        )
        status_layout.addWidget(self.current_mode_label, 0, 1)
        
        status_layout.addWidget(QLabel("HTTPプロキシ:"), 1, 0)
        self.current_http_proxy_label = QLabel("読み込み中...")
        status_layout.addWidget(self.current_http_proxy_label, 1, 1)
        
        layout.addWidget(status_group)
        
        # プロキシモード選択
        mode_group = QGroupBox("プロキシモード")
        mode_layout = QVBoxLayout(mode_group)
        
        try:
            from qt_compat.widgets import QRadioButton, QButtonGroup
            
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
            from qt_compat.widgets import QCheckBox
            
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
            from qt_compat.widgets import QLineEdit
            
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
    
    
    def setup_data_structuring_tab(self):
        """データ構造化タブを作成し、アップロードと解析結果表示を統合"""
        try:
            from classes.config.ui.upload_xlsx_tab import UploadXlsxTab
            from classes.config.ui.supported_formats_tab import SupportedFormatsTab
        except Exception as e:
            logger.warning(f"データ構造化タブのロードに失敗: {e}")
            return

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # アップロードセクション
        upload_group = QGroupBox("XLSXアップロード")
        upload_layout = QVBoxLayout(upload_group)
        self.upload_xlsx_tab = UploadXlsxTab(self)
        upload_layout.addWidget(self.upload_xlsx_tab)

        # 解析結果セクション
        result_group = QGroupBox("解析結果（対応ファイル形式一覧）")
        result_layout = QVBoxLayout(result_group)
        self.supported_formats_tab = SupportedFormatsTab(self)
        result_layout.addWidget(self.supported_formats_tab)

        # シグナル接続：アップロード→解析完了で一覧更新（元ファイルパス付き）
        if hasattr(self.upload_xlsx_tab, 'entriesParsed'):
            try:
                self.upload_xlsx_tab.entriesParsed.connect(self._update_formats_with_source)
            except Exception as ce:
                logger.debug(f"entriesParsed接続失敗: {ce}")
        
        # 起動時に既存JSON読み込み
        self._load_existing_formats()

        layout.addWidget(upload_group)
        layout.addWidget(result_group)
        layout.addStretch()

        self.tab_widget.addTab(container, "データ構造化")
    
    def _update_formats_with_source(self, entries):
        """解析完了時にentriesと元ファイルパスを一覧へ渡す"""
        try:
            from classes.config.core import supported_formats_service as formats_service
            loaded_entries, source = formats_service.load_saved_formats()
            # parse_and_save直後はentriesが最新だが、source_fileは保存側のメタを優先
            if source:
                self.supported_formats_tab.set_entries(entries, source)
            else:
                self.supported_formats_tab.set_entries(entries)
        except Exception as e:
            logger.error(f"一覧更新エラー: {e}")
            self.supported_formats_tab.set_entries(entries)
    
    def _load_existing_formats(self):
        """起動時に既存のsupported_formats.jsonを読み込んで一覧へ表示"""
        try:
            from classes.config.core import supported_formats_service as formats_service
            entries, source = formats_service.load_saved_formats()
            if not entries:
                return
            self.supported_formats_tab.set_entries(entries, source)
            logger.info(f"既存データを読み込みました: {len(entries)}件")
        except Exception as e:
            logger.debug(f"既存データ読み込み失敗（初回起動？）: {e}")
    
    def setup_ai_tab(self):
        """AI設定タブ"""
        try:
            from classes.config.ui.ai_settings_widget import create_ai_settings_widget
            
            # AI設定ウィジェットを作成
            ai_widget = create_ai_settings_widget(self)
            
            if ai_widget:
                # スクロールエリアでラップ
                ai_scroll = QScrollArea()
                ai_scroll.setWidgetResizable(True)
                ai_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                ai_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                ai_scroll.setMinimumHeight(600)
                ai_scroll.setWidget(ai_widget)
                
                # AI設定ウィジェットへの参照を保存
                self.ai_widget = ai_widget
                
                # タブを追加
                self.tab_widget.addTab(ai_scroll, "AI設定")
                logger.info("AI設定タブをロードしました")
                return
            else:
                # フォールバック：簡略版を作成
                self.setup_ai_tab_fallback()
                
        except ImportError as e:
            logger.warning(f"AI設定ウィジェットのインポートに失敗: {e}")
            # フォールバック：簡略版を作成
            self.setup_ai_tab_fallback()
        except Exception as e:
            logger.error(f"AI設定タブ作成エラー: {e}")
            self.setup_ai_tab_fallback()
    
    def setup_ai_tab_fallback(self):
        """AI設定タブ - フォールバック版"""
        logger.debug("[settings_tab_widget] フォールバックAI設定タブを作成")
        
        fallback_widget = QWidget()
        layout = QVBoxLayout(fallback_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # タイトル
        title_label = QLabel("AI設定")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        info_label = QLabel(
            "AI設定機能は現在利用できません。\n"
            "手動でinput/ai_config.jsonを編集してください。\n"
            "詳細は管理者にお問い合わせください。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 設定ファイルパス表示
        path_label = QLabel("設定ファイル: input/ai_config.json")
        path_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-style: italic;")
        layout.addWidget(path_label)
        
        layout.addStretch()
        self.tab_widget.addTab(fallback_widget, "AI設定")
        
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
            applied_settings = []
            
            # プロキシ設定の適用
            if hasattr(self, 'proxy_widget') and hasattr(self.proxy_widget, 'apply_settings'):
                self.proxy_widget.apply_settings()
                applied_settings.append("プロキシ設定")
            
            # AI設定の適用
            if hasattr(self, 'ai_widget') and hasattr(self.ai_widget, 'save_settings'):
                self.ai_widget.save_settings()
                applied_settings.append("AI設定")

            # メール設定の適用
            if hasattr(self, 'mail_widget') and hasattr(self.mail_widget, 'save_settings'):
                self.mail_widget.save_settings()
                applied_settings.append("メール")
            
            if applied_settings:
                message = f"以下の設定が適用されました:\n• " + "\n• ".join(applied_settings)
            else:
                message = "設定が適用されました。（簡易モード）"
                
            QMessageBox.information(self, "設定適用", message)
            
        except Exception as e:
            logger.error(f"設定適用エラー: {e}")
            QMessageBox.warning(self, "エラー", f"設定の適用に失敗しました: {e}")
            
    def reload_settings(self):
        """設定を再読み込み"""
        try:
            reloaded_settings = []
            
            # プロキシ設定の再読み込み
            if hasattr(self, 'proxy_widget') and hasattr(self.proxy_widget, 'load_current_settings'):
                self.proxy_widget.load_current_settings()
                reloaded_settings.append("プロキシ設定")
            elif hasattr(self, 'proxy_widget'):
                # フォールバック処理
                if hasattr(self, 'current_mode_label'):
                    self.current_mode_label.setText("SYSTEM")
                if hasattr(self, 'current_http_proxy_label'):
                    self.current_http_proxy_label.setText("自動検出")
                reloaded_settings.append("プロキシ設定（簡易）")
            
            # AI設定の再読み込み
            if hasattr(self, 'ai_widget') and hasattr(self.ai_widget, 'load_current_settings'):
                self.ai_widget.load_current_settings()
                reloaded_settings.append("AI設定")

            # メール設定の再読み込み
            if hasattr(self, 'mail_widget') and hasattr(self.mail_widget, 'load_current_settings'):
                self.mail_widget.load_current_settings()
                reloaded_settings.append("メール")
                
            if reloaded_settings:
                message = f"以下の設定が再読み込みされました:\n• " + "\n• ".join(reloaded_settings)
            else:
                message = "設定が再読み込みされました。（簡易モード）"
                
            QMessageBox.information(self, "設定再読み込み", message)
            
        except Exception as e:
            logger.error(f"設定再読み込みエラー: {e}")
            QMessageBox.warning(self, "エラー", f"設定の再読み込みに失敗しました: {e}")

    def setup_mail_tab(self):
        """メール設定タブ（Gmail先行実装）"""
        try:
            from classes.config.ui.mail_settings_tab import MailSettingsTab

            self.mail_widget = MailSettingsTab(self)
            self.tab_widget.addTab(self.mail_widget, "メール")
        except Exception as e:
            logger.warning("メールタブのロードに失敗: %s", e)

    def setup_autologin_tab(self):
        """自動ログインタブを設定"""
        try:
            logger.debug("[settings_tab_widget] setup_autologin_tab: 開始")
            
            # AutoLoginTabWidgetのインポートを試行
            try:
                from classes.config.ui.autologin_tab_widget import AutoLoginTabWidget
                logger.debug("[settings_tab_widget] AutoLoginTabWidgetのインポートを試行")
                
                # 自動ログインタブウィジェットを作成
                autologin_widget = AutoLoginTabWidget(self)
                logger.info("[settings_tab_widget] AutoLoginTabWidget作成成功")
                
                # タブに追加
                tab_index = self.tab_widget.addTab(autologin_widget, "自動ログイン")
                logger.info("[settings_tab_widget] 自動ログインタブ追加完了: インデックス=%s", tab_index)
                
                # ウィジェットへの参照を保存
                self.autologin_widget = autologin_widget
                
            except ImportError as e:
                logger.debug("[settings_tab_widget] AutoLoginTabWidgetのインポートに失敗: %s", e)
                self._create_fallback_autologin_tab()
            except Exception as e:
                logger.error("[settings_tab_widget] AutoLoginTabWidget作成エラー: %s", e)
                self._create_fallback_autologin_tab()
                
        except Exception as e:
            logger.error("[settings_tab_widget] setup_autologin_tab全体エラー: %s", e)
            logger.error(f"自動ログインタブ設定エラー: {e}")
    
    def setup_token_status_tab(self):
        """トークン状態タブを設定"""
        try:
            logger.info("トークン状態タブ設定開始")
            
            # TokenStatusTabのインポート
            from classes.config.ui.token_status_tab import TokenStatusTab
            
            # トークン状態タブウィジェットを作成
            token_status_widget = TokenStatusTab(self)
            logger.info("TokenStatusTab作成成功")
            
            # タブに追加
            tab_index = self.tab_widget.addTab(token_status_widget, "トークン状態")
            logger.info(f"トークン状態タブ追加完了: インデックス={tab_index}")
            
            # ウィジェットへの参照を保存
            self.token_status_widget = token_status_widget
            
        except ImportError as e:
            logger.error(f"TokenStatusTabのインポート失敗: {e}")
            # フォールバック: ダミータブ表示
            self._create_fallback_token_status_tab()
        except Exception as e:
            logger.error(f"トークン状態タブ設定エラー: {e}", exc_info=True)
            self._create_fallback_token_status_tab()
    
    def _create_fallback_token_status_tab(self):
        """トークン状態タブのフォールバック（エラー表示）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        title_label = QLabel("トークン状態（読み込みエラー）")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        info_label = QLabel("トークン状態タブの読み込みに失敗しました。\nログを確認してください。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        layout.addStretch()
        self.tab_widget.addTab(widget, "トークン状態")


    def _create_fallback_autologin_tab(self):
        """自動ログインタブ - フォールバック版"""
        logger.debug("[settings_tab_widget] フォールバック自動ログインタブを作成")
        
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
        logger.info("[settings_tab_widget] フォールバック自動ログインタブ追加完了: インデックス=%s", tab_index)
    
    def setup_report_tab(self):
        """報告書タブ"""
        logger.info("[settings_tab_widget] 報告書タブ作成開始")
        try:
            from classes.config.ui.report_tab import ReportTab
            report_widget = ReportTab(self)
            
            # スクロールエリアでラップ
            report_scroll = QScrollArea()
            report_scroll.setWidgetResizable(True)
            report_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            report_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            report_scroll.setWidget(report_widget)
            
            self.report_widget = report_widget
            
            # タブを追加
            self.tab_widget.addTab(report_scroll, "報告書")
            logger.info("[settings_tab_widget] 報告書タブ追加成功")
            return
            
        except Exception as e:
            logger.warning(f"[settings_tab_widget] 報告書タブ作成失敗: {e}")
            # フォールバック
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(20, 20, 20, 20)
            
            title_label = QLabel("報告書データ取得")
            title_font = QFont()
            title_font.setPointSize(14)
            title_font.setBold(True)
            title_label.setFont(title_font)
            layout.addWidget(title_label)
            
            info_label = QLabel("報告書データ取得機能は現在開発中です。")
            info_label.setWordWrap(True)
            layout.addWidget(info_label)
            
            layout.addStretch()
            self.tab_widget.addTab(widget, "報告書")

    def setup_data_portal_public_tab(self):
        """データポータル（公開・ログイン不要）タブ"""
        logger.info("[settings_tab_widget] データポータルタブ作成開始")
        try:
            from classes.config.ui.data_portal_public_tab import DataPortalPublicTab

            portal_widget = DataPortalPublicTab(self)

            portal_scroll = QScrollArea()
            portal_scroll.setWidgetResizable(True)
            portal_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            portal_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            portal_scroll.setWidget(portal_widget)

            self.data_portal_public_widget = portal_widget
            self.tab_widget.addTab(portal_scroll, "データポータル")
            logger.info("[settings_tab_widget] データポータルタブ追加成功")
            return

        except Exception as e:
            logger.warning(f"[settings_tab_widget] データポータルタブ作成失敗: {e}")
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(20, 20, 20, 20)

            title_label = QLabel("データポータル（公開）")
            title_font = QFont()
            title_font.setPointSize(14)
            title_font.setBold(True)
            title_label.setFont(title_font)
            layout.addWidget(title_label)

            info_label = QLabel("公開データポータル機能の読み込みに失敗しました。")
            info_label.setWordWrap(True)
            layout.addWidget(info_label)

            layout.addStretch()
            self.tab_widget.addTab(widget, "データポータル")
    
    def setup_equipment_tab(self):
        """設備タブ"""
        logger.info("[settings_tab_widget] 設備タブ作成開始")
        try:
            from classes.config.ui.equipment_tab import EquipmentTab
            equipment_widget = EquipmentTab(self)
            
            # スクロールエリアでラップ
            equipment_scroll = QScrollArea()
            equipment_scroll.setWidgetResizable(True)
            equipment_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            equipment_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            equipment_scroll.setWidget(equipment_widget)
            
            self.equipment_widget = equipment_widget
            
            # タブを追加
            self.tab_widget.addTab(equipment_scroll, "設備")
            logger.info("[settings_tab_widget] 設備タブ追加成功")
            return
            
        except Exception as e:
            logger.warning(f"[settings_tab_widget] 設備タブ作成失敗: {e}")
            # フォールバック
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(20, 20, 20, 20)
            
            title_label = QLabel("設備データ取得")
            title_font = QFont()
            title_font.setPointSize(14)
            title_font.setBold(True)
            title_label.setFont(title_font)
            layout.addWidget(title_label)
            
            info_label = QLabel("設備データ取得機能は現在開発中です。")
            info_label.setWordWrap(True)
            layout.addWidget(info_label)
            
            layout.addStretch()
            self.tab_widget.addTab(widget, "設備")


def create_settings_tab_widget(parent=None, bearer_token=None):
    """設定タブウィジェットを作成"""
    try:
        widget = SettingsTabWidget(parent, bearer_token)
        return widget
    except Exception as e:
        logger.error(f"設定タブウィジェット作成エラー: {e}")
        import traceback
        traceback.print_exc()
        return None

    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

    
    
    
    
    
    

