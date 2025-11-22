"""
メインウィンドウタブ統合機能
設定ダイアログをメインウィンドウのタブとして統合する機能

主要機能:
- 既存のメニューエリアをタブウィジェットに変換
- 設定タブの追加とレスポンシブ対応
- 画面サイズに応じた最適レイアウト
"""

import logging
from typing import Optional
from classes.theme import get_color, ThemeKey

try:
    from qt_compat.widgets import (
        QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QApplication
    )
    from qt_compat.core import Qt
    from qt_compat.gui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QTabWidget: pass
    class QWidget: pass

logger = logging.getLogger(__name__)

class MainWindowTabIntegrator:
    """メインウィンドウにタブ機能を統合するクラス"""
    
    def __init__(self, parent):
        self.parent = parent
        self.tab_widget = None
        self.settings_tab = None
        
    def integrate_tabs(self):
        """メインウィンドウにタブ機能を統合"""
        if not PYQT5_AVAILABLE:
            logger.warning("PyQt5が利用できないため、タブ統合をスキップします")
            return False
            
        try:
            # 既存のメニューエリアをタブウィジェットに変換
            if hasattr(self.parent, 'menu_area_widget') and hasattr(self.parent, 'menu_area_layout'):
                self._convert_menu_area_to_tabs()
                return True
            else:
                logger.warning("メニューエリアが見つからないため、タブ統合を実行できません")
                return False
                
        except Exception as e:
            logger.error(f"タブ統合エラー: {e}")
            return False
            
    def _convert_menu_area_to_tabs(self):
        """メニューエリアをタブウィジェットに変換"""
        # 既存のメニューエリアウィジェットを取得
        menu_area_widget = self.parent.menu_area_widget
        menu_area_layout = self.parent.menu_area_layout
        
        # 既存の内容をクリア
        while menu_area_layout.count():
            child = menu_area_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        
        # タブウィジェットを作成
        self.tab_widget = QTabWidget()
        
        # タブ切り替えイベントを接続
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        
        # 既存の機能タブを作成
        self._create_main_functions_tab()
        
        # 設定タブを追加
        self._add_settings_tab()
        
        # 報告書タブを追加（v2.1.0新機能）
        self._add_reports_tab()
        
        # ヘルプタブを追加（v2.1.3新機能）
        self._add_help_tab()
        
        # タブウィジェットをメニューエリアに追加
        menu_area_layout.addWidget(self.tab_widget)
        
        # 親ウィジェットにタブウィジェットを保存
        self.parent.tabs = self.tab_widget
        
        logger.info("メニューエリアがタブウィジェットに変換されました")
        
    def _create_main_functions_tab(self):
        """メイン機能タブを作成"""
        main_tab = QWidget()
        layout = QVBoxLayout(main_tab)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # タイトル
        title_label = QLabel("メイン機能")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        info_label = QLabel(
            "左側のメニューボタンから各機能を選択してください。\\n"
            "選択された機能の詳細設定がここに表示されます。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 現在のモード表示
        self.current_mode_label = QLabel("現在のモード: 初期化中")
        self.current_mode_label.setStyleSheet("font-weight: bold; color: blue; padding: 5px;")
        layout.addWidget(self.current_mode_label)
        
        # 状態表示エリア
        status_label = QLabel("状態情報")
        status_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(status_label)
        
        self.status_info_label = QLabel("準備完了")
        self.status_info_label.setStyleSheet(f"padding: 5px; background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)}; border-radius: 3px;")
        layout.addWidget(self.status_info_label)
        
        layout.addStretch()
        
        # メイン機能タブとして追加
        self.tab_widget.addTab(main_tab, "メイン機能")
        
        # 親オブジェクトに参照を保存（他のコードからアクセス可能にする）
        self.parent.main_functions_tab = main_tab
        self.parent.current_mode_label = self.current_mode_label
        self.parent.status_info_label = self.status_info_label
        
    def _add_settings_tab(self):
        """設定タブを追加"""
        try:
            from classes.config.ui.settings_tab_widget import create_settings_tab_widget
            
            # 設定タブウィジェットを作成
            self.settings_tab = create_settings_tab_widget(self.parent, getattr(self.parent, 'bearer_token', None))
            
            if self.settings_tab:
                self.tab_widget.addTab(self.settings_tab, "設定")
                logger.info("設定タブが追加されました")
            else:
                # フォールバック：簡単な設定タブを作成
                self._create_fallback_settings_tab()
                
        except ImportError as e:
            logger.warning(f"設定タブウィジェットのインポートに失敗: {e}")
            self._create_fallback_settings_tab()
        except Exception as e:
            logger.error(f"設定タブ追加エラー: {e}")
            self._create_fallback_settings_tab()
            
    def _create_fallback_settings_tab(self):
        """フォールバック用簡易設定タブ"""
        settings_tab = QWidget()
        layout = QVBoxLayout(settings_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # タイトル
        title_label = QLabel("設定")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        info_label = QLabel("設定機能は準備中です。")
        layout.addWidget(info_label)
        
        # 従来の設定ダイアログを開くボタン
        open_settings_btn = QPushButton("設定ダイアログを開く")
        open_settings_btn.clicked.connect(self._open_legacy_settings_dialog)
        layout.addWidget(open_settings_btn)
        
        layout.addStretch()
        
        self.tab_widget.addTab(settings_tab, "設定")
        self.settings_tab = settings_tab
    
    def _add_reports_tab(self):
        """報告書タブを追加（v2.1.0新機能）"""
        try:
            from classes.reports.ui.report_widget import ReportWidget
            
            # 報告書タブウィジェットを作成
            self.reports_tab = ReportWidget()
            
            if self.reports_tab:
                self.tab_widget.addTab(self.reports_tab, "📋 報告書")
                logger.info("報告書タブが追加されました")
            else:
                logger.warning("報告書タブの作成に失敗しました")
                
        except ImportError as e:
            logger.warning(f"報告書タブウィジェットのインポートに失敗: {e}")
            self._create_fallback_reports_tab()
        except Exception as e:
            logger.error(f"報告書タブ追加エラー: {e}")
            self._create_fallback_reports_tab()
            
    def _create_fallback_reports_tab(self):
        """フォールバック用簡易報告書タブ"""
        reports_tab = QWidget()
        layout = QVBoxLayout(reports_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # タイトル
        title_label = QLabel("📋 報告書")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        info_label = QLabel("報告書機能のインポートに失敗しました。")
        info_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        self.tab_widget.addTab(reports_tab, "📋 報告書")
        self.reports_tab = reports_tab
        
    def _open_legacy_settings_dialog(self):
        """従来の設定ダイアログを開く"""
        try:
            from classes.config.ui.settings_dialog import run_settings_logic
            run_settings_logic(self.parent, getattr(self.parent, 'bearer_token', None))
        except Exception as e:
            logger.error(f"設定ダイアログ起動エラー: {e}")
            try:
                from qt_compat.widgets import QMessageBox
                QMessageBox.warning(self.parent, "エラー", f"設定ダイアログの起動に失敗しました: {e}")
            except:
                logger.error("設定ダイアログエラー: %s", e)
    
    def _add_help_tab(self):
        """ヘルプタブを追加（v2.1.3新機能）"""
        try:
            # ヘルプタブウィジェットを作成
            help_tab = self._create_help_tab_widget()
            
            if help_tab:
                self.tab_widget.addTab(help_tab, "ヘルプ")
                logger.info("ヘルプタブが追加されました")
                self.help_tab = help_tab
            else:
                logger.warning("ヘルプタブの作成に失敗しました")
                
        except Exception as e:
            logger.error(f"ヘルプタブ追加エラー: {e}")
    
    def _create_help_tab_widget(self):
        """ヘルプタブウィジェットを作成"""
        help_tab = QWidget()
        layout = QVBoxLayout(help_tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # タイトル
        title_label = QLabel("ヘルプ")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        info_label = QLabel(
            "アプリケーションの使用方法やライセンス情報を確認できます。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # ヘルプダイアログを開くボタン
        open_help_btn = QPushButton("ヘルプを開く")
        open_help_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                font-size: 14px;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
        """)
        open_help_btn.clicked.connect(self._open_help_dialog)
        layout.addWidget(open_help_btn)
        
        # クイックヘルプセクション
        quick_help_label = QLabel("クイックヘルプ")
        quick_help_label.setStyleSheet("font-weight: bold; margin-top: 15px;")
        layout.addWidget(quick_help_label)
        
        quick_help_text = QLabel(
            "• 左側のメニューから機能を選択してください\n"
            "• 設定メニューからアプリケーション設定を変更できます\n"
            "• トークン状態タブでBearer Tokenの有効期限を確認できます\n"
            "• プロキシ設定はネットワーク設定タブで行います"
        )
        quick_help_text.setWordWrap(True)
        quick_help_text.setStyleSheet(f"padding: 10px; background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)}; border-radius: 5px;")
        layout.addWidget(quick_help_text)
        
        layout.addStretch()
        
        return help_tab
    
    def _open_help_dialog(self):
        """ヘルプダイアログを開く"""
        try:
            from classes.help.ui.help_dialog import show_help_dialog
            show_help_dialog(self.parent)
            logger.info("ヘルプダイアログを開きました")
        except Exception as e:
            logger.error(f"ヘルプダイアログ起動エラー: {e}")
            try:
                from qt_compat.widgets import QMessageBox
                QMessageBox.warning(self.parent, "エラー", f"ヘルプダイアログの起動に失敗しました: {e}")
            except:
                logger.error("ヘルプダイアログエラー: %s", e)
                
    def update_current_mode(self, mode: str):
        """現在のモードを更新"""
        if hasattr(self, 'current_mode_label'):
            mode_names = {
                'login': 'ログイン',
                'data_fetch': 'データ取得',
                'dataset_open': 'データセット開設',
                'data_register': 'データ登録',
                'subgroup_create': 'サブグループ作成',
                'ai_test': 'AI分析',
                'settings': '設定'
            }
            display_name = mode_names.get(mode, mode)
            self.current_mode_label.setText(f"現在のモード: {display_name}")
            
    def update_status_info(self, status: str):
        """状態情報を更新"""
        if hasattr(self, 'status_info_label'):
            self.status_info_label.setText(status)
            
    def get_optimal_tab_width(self):
        """最適なタブ幅を計算"""
        if not PYQT5_AVAILABLE:
            return 800
            
        try:
            # 親ウィンドウまたは画面サイズを取得
            if self.parent:
                width = self.parent.width()
            else:
                # PySide6対応
                from qt_compat import get_screen_size
                width, _ = get_screen_size()
            
            # 利用可能な幅からメニュー部分を除く
            available_width = width - 160  # メニュー幅 + マージン
            
            # 最小・最大幅を設定
            min_width = 600
            max_width = 1400
            
            return max(min_width, min(available_width, max_width))
            
        except Exception as e:
            logger.warning(f"最適タブ幅計算エラー: {e}")
            return 800
            
    def adjust_layout_for_screen_size(self):
        """画面サイズに応じてレイアウトを調整"""
        if not self.tab_widget:
            return
            
        try:
            optimal_width = self.get_optimal_tab_width()
            
            # タブウィジェットの幅を調整
            if hasattr(self.tab_widget, 'setMinimumWidth'):
                self.tab_widget.setMinimumWidth(optimal_width)
                
            # 設定タブのレイアウト調整
            if self.settings_tab and hasattr(self.settings_tab, 'get_optimal_layout_columns'):
                # 段組数を再計算して適用
                columns = self.settings_tab.get_optimal_layout_columns()
                logger.info(f"画面サイズに応じて設定タブを{columns}段組に調整")
                
        except Exception as e:
            logger.warning(f"レイアウト調整エラー: {e}")
    
    def _on_tab_changed(self, index: int):
        """タブが切り替えられたときの処理"""
        try:
            # タブの名前を取得
            tab_name = self.tab_widget.tabText(index)
            logger.debug(f"タブ切り替え: {tab_name} (index={index})")
            
            # 基本情報タブが表示された場合、自動検証を実行
            if "基本情報" in tab_name or "メイン機能" in tab_name:
                self._trigger_basic_info_validation()
                
        except Exception as e:
            logger.error(f"タブ切り替え処理エラー: {e}")
    
    def _trigger_basic_info_validation(self):
        """基本情報タブの自動検証を起動"""
        try:
            # UIコントローラーから基本情報タブバリデータを取得
            if hasattr(self.parent, 'ui_controller'):
                ui_controller = self.parent.ui_controller
                
                # バリデータが存在する場合は検証を実行
                if hasattr(ui_controller, 'basic_info_tab_validator'):
                    validator = ui_controller.basic_info_tab_validator
                    validator.validate_on_tab_shown()
                    logger.debug("基本情報タブの自動検証を起動しました")
                else:
                    logger.debug("基本情報タブバリデータが未初期化です")
            else:
                logger.debug("UIコントローラーが見つかりません")
                
        except Exception as e:
            logger.error(f"基本情報タブ自動検証の起動エラー: {e}")


def integrate_settings_into_main_window(parent):
    """メインウィンドウに設定タブを統合する関数"""
    try:
        integrator = MainWindowTabIntegrator(parent)
        success = integrator.integrate_tabs()
        
        if success:
            # 統合オブジェクトを親に保存
            parent.tab_integrator = integrator
            logger.info("設定タブがメインウィンドウに正常に統合されました")
            return integrator
        else:
            logger.error("設定タブの統合に失敗しました")
            return None
            
    except Exception as e:
        logger.error(f"設定タブ統合処理でエラーが発生: {e}")
        return None
