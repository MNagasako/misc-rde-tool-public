"""
UIコントローラー基盤クラス - ARIM RDE Tool v1.13.1
UIControllerの基本機能・初期化・モード管理を担当
"""
import logging
from qt_compat.widgets import QPushButton, QVBoxLayout, QWidget
from qt_compat.core import QTimer
from qt_compat.gui import QFontMetrics

logger = logging.getLogger("RDE_WebView")

class UIControllerCore:
    """UIコントローラーの基盤機能クラス"""
    
    def __init__(self, parent_widget):
        """
        UIコントローラーコアの初期化
        Args:
            parent_widget: 親ウィジェット（Browserクラスのインスタンス）
        """
        self.parent = parent_widget
        self.current_mode = "login"  # 初期モードをloginに設定
        self.menu_buttons = {}
        
        # データ取得モード用のウィジェットとレイアウト
        self.data_fetch_widget = None
        self.data_fetch_layout = None
        
        # 試料選択用の変数
        self.selected_sample_id = None
        
        # 他のモード用ウィジェット
        self.dataset_open_widget = None
        self.data_register_widget = None
        self.settings_widget = None
        self.data_portal_widget = None
        
        # 画像取得上限設定用
        self.image_limit_dropdown = None
        
        # リクエスト解析GUI用
        self.analyzer_gui = None
        
        # オーバーレイ制御フラグ
        self.overlay_disabled_for_analyzer = False
        # ログイン完了フラグ
        self.login_completed = False
        
        # AI機能用の変数
        self.last_request_content = ""  # 最後のリクエスト内容を保存
        self.last_response_info = {}    # 最後のレスポンス情報を保存（モデル、時間等）
        self.current_arim_data = None   # 現在読み込まれているARIM拡張データ
        
        # AI機能データ管理クラスの初期化
        try:
            from classes.ai.core.ai_data_manager import AIDataManager
            self.ai_data_manager = AIDataManager(logger=getattr(parent_widget, 'logger', None))
            logger.debug("AIDataManager初期化完了")
        except Exception as e:
            logger.debug("AIDataManager初期化エラー: %s", e)
            self.ai_data_manager = None
        
        # AIPromptManager初期化 
        try:
            from classes.ai.util.ai_prompt_manager import AIPromptManager
            self.ai_prompt_manager = AIPromptManager(logger=getattr(parent_widget, 'logger', None))
            logger.debug("AIPromptManager初期化完了")
        except Exception as e:
            logger.debug("AIPromptManager初期化エラー: %s", e)
            self.ai_prompt_manager = None
        
        # ログ設定
        self.logger = logging.getLogger("UIControllerCore")
    
    def adjust_button_font_size(self, button, max_width=None, max_height=None):
        """
        ボタンのテキストが収まるようにフォントサイズを自動調整（安全性チェック付き）
        Args:
            button: QPushButton オブジェクト
            max_width: ボタンの最大幅（Noneの場合はボタンの現在の幅を使用）
            max_height: ボタンの最大高さ（Noneの場合はボタンの現在の高さを使用）
        """
        try:
            # ボタンオブジェクトの有効性をチェック
            if button is None or not hasattr(button, 'text') or not hasattr(button, 'width'):
                return
            if max_width is None:
                max_width = button.width() - 10  # パディングを考慮
            if max_height is None:
                max_height = button.height() - 8  # パディングを考慮
            text = button.text()
            font = button.font()
            # 最小・最大フォントサイズを設定
            min_font_size = 8
            max_font_size = 10
            low, high = min_font_size, max_font_size
            best_size = min_font_size
            while low <= high:
                mid = (low + high) // 2
                font.setPointSize(mid)
                metrics = QFontMetrics(font)
                text_width = metrics.horizontalAdvance(text)
                text_height = metrics.height()
                if text_width <= max_width and text_height <= max_height:
                    best_size = mid
                    low = mid + 1
                else:
                    high = mid - 1
            # 最適なフォントサイズを設定
            font.setPointSize(best_size)
            button.setFont(font)
        except (RuntimeError, AttributeError):
            # オブジェクトが削除済みまたは属性がない場合は無視
            pass
    
    def create_auto_resize_button(self, text, width, height, base_style):
        """
        フォントサイズ自動調整機能付きのボタンを作成
        Args:
            text: ボタンのテキスト
            width: ボタンの幅
            height: ボタンの高さ
            base_style: ベースのスタイル
        Returns:
            QPushButton: 作成されたボタン
        """
        button = QPushButton(text)
        button.setFixedSize(width, height)
        button.setStyleSheet(base_style)
        
        # ボタンが表示された後にフォントサイズを調整（安全性チェック付き）
        def adjust_font():
            try:
                # ボタンオブジェクトが削除されていないかチェック
                if button is not None and hasattr(button, 'isVisible') and button.isVisible():
                    self.adjust_button_font_size(button, width - 10, height - 2)
            except (RuntimeError, AttributeError):
                # オブジェクトが削除済みまたは属性がない場合は無視
                pass
        
        QTimer.singleShot(100, adjust_font)  # 少し遅延させて確実に調整
        
        return button
        
    def get_data_fetch_layout(self):
        """
        データ取得レイアウトを取得
        Returns:
            QVBoxLayout: データ取得レイアウト
        """
        # データ取得ウィジェットが存在しない場合は作成
        if self.data_fetch_widget is None:
            self.data_fetch_widget = QWidget()
            self.data_fetch_layout = QVBoxLayout()
            self.data_fetch_widget.setLayout(self.data_fetch_layout)
        
        return self.data_fetch_layout
    
    def get_current_mode(self):
        """
        現在のモードを取得
        Returns:
            str: 現在のモード
        """
        return self.current_mode
    
    def adjust_window_height_to_contents(self):
        """
        ウィンドウの高さをコンテンツに合わせて自動調整（重なり防止機能付き）
        """
        try:
            if self.parent and hasattr(self.parent, 'central_widget'):
                # 最小高さを設定
                min_height = 600
                max_height = 900
                
                # 各メインウィジェットの推奨サイズを取得
                current_widget = None
                mode = self.get_current_mode()
                
                if mode == "data_fetch" and hasattr(self, 'data_fetch_widget') and self.data_fetch_widget:
                    current_widget = self.data_fetch_widget
                
                if current_widget:
                    # ウィジェットの推奨サイズを取得
                    size_hint = current_widget.sizeHint()
                    content_height = max(size_hint.height(), min_height)
                    content_height = min(content_height, max_height)
                    
                    # ウィンドウ枠などのマージンを追加
                    total_height = content_height + 100
                    
                    # ウィンドウサイズを設定
                    self.parent.resize(self.parent.width(), total_height)
        except (AttributeError, RuntimeError) as e:
            # エラーが発生した場合はログ出力のみ
            self.logger.warning(f"ウィンドウ高さ調整エラー: {e}")
    
    def update_message_labels_position(self, mode):
        """
        メッセージラベルの位置をモードに応じて更新
        Args:
            mode: 現在のモード
        """
        try:
            if hasattr(self.parent, 'display_manager') and self.parent.display_manager:
                # モード別の位置調整
                if mode == "data_fetch":
                    # データ取得モードでは下部に配置
                    pass
                elif mode == "login":
                    # ログインモードでは中央下部に配置
                    pass
        except (AttributeError, RuntimeError) as e:
            self.logger.warning(f"メッセージラベル位置更新エラー: {e}")

    def center_window(self):
        """
        ウィンドウを画面中央に移動
        """
        try:
            from qt_compat.widgets import QApplication
            
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                window_geometry = self.parent.frameGeometry()
                center_point = screen_geometry.center()
                window_geometry.moveCenter(center_point)
                self.parent.move(window_geometry.topLeft())
        except Exception as e:
            logger.error("ウィンドウ中央移動エラー: %s", e)
    
    def show_grant_number_form(self):
        """
        課題番号入力フォームの表示
        """
        try:
            import os
            from qt_compat.widgets import QHBoxLayout, QLineEdit, QLabel, QPushButton
            from qt_compat.core import QUrl
            from qt_compat.gui import QDesktopServices
            from config.common import DATASETS_DIR, get_dynamic_file_path
            from functions.utils import wait_for_form_and_click_button
            
            # 既存フォームが存在する場合は有効化のみ
            if hasattr(self.parent, 'grant_input') and self.parent.grant_input is not None:
                self.parent.grant_input.setDisabled(False)
                self.parent.grant_btn.setDisabled(False)
                return
            
            form_layout = QHBoxLayout()
            self.parent.grant_input = QLineEdit(self.parent.grant_number)
            self.parent.grant_input.setObjectName('grant_input')
            form_layout.addWidget(QLabel('ARIM課題番号:'))
            form_layout.addWidget(self.parent.grant_input)
            
            # 実行ボタン作成
            self.parent.grant_btn = self.create_auto_resize_button(
                '実行', 120, 36, 'background-color: #1976d2; color: white; font-weight: bold; border-radius: 6px;'
            )
            self.parent.grant_btn.setObjectName('grant_btn')
            self.parent.grant_btn.clicked.connect(self.parent.on_grant_number_decided)
            form_layout.addWidget(self.parent.grant_btn)

            # 保存先フォルダを開くボタン
            open_folder_btn = QPushButton("保存先フォルダを開く")
            def on_open_folder():
                QDesktopServices.openUrl(QUrl.fromLocalFile(DATASETS_DIR))
            open_folder_btn.clicked.connect(on_open_folder)
            form_layout.addWidget(open_folder_btn)

            # データ取得モード専用のウィジェットに追加
            data_fetch_layout = self.get_data_fetch_layout()
            data_fetch_layout.addLayout(form_layout)
            self.parent.grant_form_layout = form_layout

            # 画像取得上限設定を追加
            image_limit_layout = self.create_image_limit_dropdown()
            if image_limit_layout:
                data_fetch_layout.addLayout(image_limit_layout)

            # 結果表示用ラベル
            self.parent.result_label = QLabel()
            data_fetch_layout.addWidget(self.parent.result_label)
            
            # 一括実行ボタン
            list_txt_path = get_dynamic_file_path('input/list.txt')
            if os.path.exists(list_txt_path):
                self.parent.batch_btn = self.create_auto_resize_button(
                    '一括実行', 120, 36, 'background-color: #ff9800; color: white; font-weight: bold; border-radius: 6px;'
                )
                self.parent.batch_btn.clicked.connect(self.parent.execute_batch_grant_numbers)
                data_fetch_layout.addWidget(self.parent.batch_btn)
                self.parent.batch_msg_label = QLabel('')
                data_fetch_layout.addWidget(self.parent.batch_msg_label)
            else:
                self.parent.batch_btn = None
                self.parent.batch_msg_label = QLabel('一括処理を行うにはinput/list.txtを作成して再起動してください')
                data_fetch_layout.addWidget(self.parent.batch_msg_label)
            
            # テストモード時のみ自動クリックを追加
            wait_for_form_and_click_button(self.parent, 'grant_input', 'grant_btn', timeout=10, interval=0.5, test_mode=self.parent.test_mode)
            
        except Exception as e:
            logger.error("課題番号フォーム表示エラー: %s", e)
    
    def setup_main_layout(self):
        """
        メインレイアウトの設定
        """
        try:
            from qt_compat.widgets import QHBoxLayout, QWidget, QVBoxLayout
            
            root_layout = QHBoxLayout()

            # 左側メニュー用ウィジェット
            menu_widget = QWidget()
            menu_widget.setStyleSheet('background-color: #e0f0ff; padding: 5px;')
            menu_layout = QVBoxLayout()
            menu_layout.setSpacing(8)
            menu_layout.setContentsMargins(5, 10, 5, 10)
            
            # メニューボタンを取得
            menu_buttons = self.init_mode_widgets()
            for button in menu_buttons:
                menu_layout.addWidget(button)
            
            # 初期モード設定
            self.parent.current_mode = "login"
            
            # 従来のメニューボタン参照を保持（互換性のため）
            self.parent.menu_btn1 = self.menu_buttons['data_fetch']
            self.parent.menu_btn2 = self.menu_buttons['dataset_open']
            self.parent.menu_btn3 = self.menu_buttons['data_register']
            self.parent.menu_btn4 = self.menu_buttons['settings']
            
            # 閉じるボタンを最下段に配置
            menu_layout.addStretch(1)
            self.parent.close_btn = self.create_auto_resize_button(
                '閉じる', 120, 32, 'background-color: #f44336; color: white; font-weight: bold; border-radius: 6px; margin: 2px;'
            )
            self.parent.close_btn.clicked.connect(self.parent.close)
            menu_layout.addWidget(self.parent.close_btn)
            menu_widget.setLayout(menu_layout)
            menu_widget.setFixedWidth(140)

            # 右側：上（WebView）・下（個別メニュー）に分割
            right_widget = QWidget()
            right_main_layout = QVBoxLayout()
            right_main_layout.setSpacing(5)
            right_main_layout.setContentsMargins(5, 5, 5, 5)
            
            # 上部：WebView + 待機メッセージ専用エリア
            webview_widget = QWidget()
            webview_widget.setObjectName('webview_widget')
            # 初期サイズを設定してネガティブサイズエラーを防止
            webview_widget.setMinimumSize(100, 50)
            
            # WebViewレイアウト（WebView + ログインコントロール）
            webview_layout = QHBoxLayout()
            webview_layout.addWidget(self.parent.webview)
            
            # ログインコントロールウィジェットを追加
            try:
                from classes.login.ui.login_control_widget import create_login_control_widget
                self.parent.login_control_widget = create_login_control_widget(
                    self.parent, 
                    self.parent.webview
                )
                self.parent.login_control_widget.setMaximumWidth(300)
                webview_layout.addWidget(self.parent.login_control_widget)
            except Exception as e:
                logger.error(f"ログインコントロールウィジェット初期化エラー: {e}")
                # エラー時はスペーサーで代替
                webview_layout.addSpacing(20)
            
            # v2.0.2: 待機メッセージ専用エリア（WebView直下に配置）
            vbox = QVBoxLayout()
            vbox.setSpacing(5)
            vbox.addLayout(webview_layout)
            
            # 待機メッセージ用の専用フレーム
            message_frame = QWidget()
            message_frame.setStyleSheet('''
                QWidget {
                    background-color: #f5f5f5;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    margin: 5px 0px;
                }
            ''')
            message_layout = QVBoxLayout()
            message_layout.setContentsMargins(10, 5, 10, 5)
            message_layout.setSpacing(3)
            
            # 待機メッセージラベル（目立つ位置）
            message_layout.addWidget(self.parent.autologin_msg_label)
            message_layout.addWidget(self.parent.webview_msg_label)
            
            message_frame.setLayout(message_layout)
            vbox.addWidget(message_frame)
            
            webview_widget.setLayout(vbox)
            
            # 下部：個別メニュー（切り替え可能エリア）
            self.parent.menu_area_widget = QWidget()
            self.parent.menu_area_layout = QVBoxLayout()
            self.parent.menu_area_layout.setContentsMargins(5, 5, 5, 5)
            self.parent.menu_area_widget.setLayout(self.parent.menu_area_layout)
            
            # 右側全体に追加
            right_main_layout.addWidget(webview_widget, 3)
            right_main_layout.addWidget(self.parent.menu_area_widget, 1)
            right_widget.setLayout(right_main_layout)

            # ルートレイアウトに左右追加
            root_layout.addWidget(menu_widget)
            root_layout.addWidget(right_widget, 1)
            self.parent.setLayout(root_layout)
            
            # タブ統合機能を追加
            self._integrate_settings_tab()
            
        except Exception as e:
            logger.error("メインレイアウト設定エラー: %s", e)
            
    def _integrate_settings_tab(self):
        """設定タブをメインウィンドウに統合"""
        try:
            from classes.ui.integrators.tab_integrator import integrate_settings_into_main_window
            
            # 設定タブを統合
            integrator = integrate_settings_into_main_window(self.parent)
            
            if integrator:
                logger.debug("設定タブがメインウィンドウに統合されました")
            else:
                logger.debug("設定タブの統合に失敗しました（従来の設定ダイアログを使用）")
                
        except ImportError as e:
            logger.debug("タブ統合機能のインポートに失敗: %s", e)
        except Exception as e:
            logger.error("設定タブ統合エラー: %s", e)
    
    def finalize_window_setup(self):
        """
        ウィンドウの表示と最終設定
        """
        try:
            import os
            from config.common import DEBUG_INFO_FILE, LOGIN_FILE
            from functions.common_funcs import external_path
            
            self.parent.show()
            self.center_window()
            
            # アスペクト比固定用
            self.parent._fixed_aspect_ratio = self.parent.width() / self.parent.height() if self.parent.height() != 0 else 1.0
            
            # ウインドウ横幅を自動調整
            menu_width = 120
            margin = 40
            webview_width = getattr(self.parent, '_webview_fixed_width', 900)
            self.parent.setMinimumWidth(webview_width + menu_width + margin)

            # login.txtのパス情報をinfo.txtに出力
            info_path = external_path(DEBUG_INFO_FILE)
            login_path = external_path(LOGIN_FILE)
            login_info = f"login.txt path : {os.path.abspath(login_path)}"

            try:
                with open(info_path, 'w', encoding='utf-8') as infof:
                    infof.write(f"{login_info}\n")
            except Exception as e:
                logger.debug("info.txt書き込み失敗: %s", e)

            self.parent.autologin_status = 'init'
            self.parent.update_autologin_msg('ブラウザ初期化完了')
            
            # test_modeでは自動ログイン処理をスキップ
            if not self.parent.test_mode:
                # v1.20.3: 自動ログイン開始時にマテリアルトークンフラグをリセット
                logger.info("[LOGIN] 自動ログイン開始 - マテリアルトークンフラグをリセット")
                self.parent.login_manager.reset_material_token_flag()
                self.parent.login_manager.poll_dice_btn_status()
            else:
                self.parent.update_autologin_msg('[TEST] テストモード - 自動ログイン処理をスキップ')
                
        except Exception as e:
            logger.error("ウィンドウ最終設定エラー: %s", e)
