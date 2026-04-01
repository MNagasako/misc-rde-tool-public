"""
UIコントローラー基盤クラス - ARIM RDE Tool
UI Controllerの基本機能・初期化・モード管理を担当
"""
import logging
from qt_compat.widgets import QPushButton, QVBoxLayout, QWidget
from qt_compat.core import QTimer
from qt_compat.gui import QFontMetrics
from classes.theme import get_color, ThemeKey, ThemeManager, ThemeMode
from classes.theme.global_styles import get_global_base_style
from classes.utils.window_sizing import (
    center_window_on_screen,
    fit_main_window_height_to_screen,
    resize_main_window,
    set_main_window_minimum_size,
)

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
        # ボタンスタイルキャッシュ
        self._button_style_cache = {}

    def _build_button_style(self, kind: str) -> str:
        """ボタン種別に応じたQSSをキャッシュして返す

        kind: primary|secondary|danger|warning|inactive|active
        """
        # テーマ切替後に旧配色が残らないよう、キャッシュキーにテーマモードを含める
        try:
            theme_mode = ThemeManager.instance().get_mode().value
        except Exception:
            theme_mode = "unknown"
        cache_key = f"{kind}:{theme_mode}"
        if cache_key in self._button_style_cache:
            return self._button_style_cache[cache_key]
        from classes.theme import get_color, ThemeKey
        mapping = {
            'primary': (ThemeKey.BUTTON_PRIMARY_BACKGROUND, ThemeKey.BUTTON_PRIMARY_TEXT),
            'secondary': (ThemeKey.BUTTON_SECONDARY_BACKGROUND, ThemeKey.BUTTON_SECONDARY_TEXT),
            'danger': (ThemeKey.BUTTON_DANGER_BACKGROUND, ThemeKey.BUTTON_DANGER_TEXT),
            'warning': (ThemeKey.BUTTON_WARNING_BACKGROUND, ThemeKey.BUTTON_WARNING_TEXT),
            'inactive': (ThemeKey.MENU_BUTTON_INACTIVE_BACKGROUND, ThemeKey.MENU_BUTTON_INACTIVE_TEXT),
            'active': (ThemeKey.BUTTON_PRIMARY_BACKGROUND, ThemeKey.BUTTON_PRIMARY_TEXT),
        }
        bg_key, fg_key = mapping.get(kind, mapping['secondary'])
        style = (
            "QPushButton { "
            f"background-color: {get_color(bg_key)}; "
            f"color: {get_color(fg_key)}; "
            "font-weight: bold; border-radius: 6px; margin: 2px; padding: 4px 8px; }"
        )
        self._button_style_cache[cache_key] = style
        return style
    
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
        
        注意: このメソッドはサイズとフォント調整のみを行います。
        スタイル（色、hover効果等）はbase_styleで完全に指定してください。
        
        Args:
            text: ボタンのテキスト
            width: ボタンの幅
            height: ボタンの高さ
            base_style: ボタンのスタイル（完全なQSS文字列）
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
    
    def _add_theme_toggle_button(self, menu_layout):
        """テーマ切替ボタンをメニューに追加
        
        Args:
            menu_layout: メニューのレイアウト
        """
        from classes.theme import ThemeManager, ThemeMode
        
        theme_manager = ThemeManager.instance()
        
        # テーマ表示用アイコン/ラベル
        theme_labels = {
            ThemeMode.LIGHT: "☀️ ライト",
            ThemeMode.DARK: "🌙 ダーク",
        }
        
        # ボタン作成
        self.theme_toggle_btn = QPushButton(theme_labels[theme_manager.get_mode()])
        self.theme_toggle_btn.setFixedSize(120, 32)
        
        def update_button_style():
            """ボタンスタイルを更新"""
            current_mode = theme_manager.get_mode()
            self.theme_toggle_btn.setText(theme_labels[current_mode])
            from classes.utils.button_styles import get_button_style

            # hover/pressed を含む共通スタイルを使用（テーマ追従は get_button_style 側で担保）
            self.theme_toggle_btn.setStyleSheet(get_button_style('secondary'))
        
        def on_theme_toggle():
            """テーマ切替ハンドラ
            
            【最適化v2.1.7】処理全体の時間を計測し遅延を可視化
            """
            import time
            toggle_start = time.perf_counter_ns()

            # テーマ切替中は操作ブロック（オーバーレイ表示）
            overlay = None
            try:
                from PySide6.QtWidgets import QApplication
                from classes.ui.utilities.theme_switch_overlay import ThemeSwitchOverlayDialog

                overlay = ThemeSwitchOverlayDialog(self.parent)
                overlay.show_centered()
                try:
                    QApplication.processEvents()
                except Exception:
                    pass
            except Exception:
                overlay = None
            
            try:
                # テーマモード変更（ThemeManager内で詳細計測）
                # 2状態トグル (AUTO廃止)
                if getattr(self.parent, 'current_mode', None) == 'data_portal':
                    try:
                        theme_manager.defer_global_stylesheet_once()
                    except Exception:
                        pass
                theme_manager.toggle_mode()
                
                # ボタン更新（軽量）
                button_start = time.perf_counter_ns()
                update_button_style()
                button_elapsed = (time.perf_counter_ns() - button_start) / 1_000_000
                
                # 全UI色再適用（重い可能性）
                refresh_start = time.perf_counter_ns()
                self._refresh_all_ui_colors()
                refresh_elapsed = (time.perf_counter_ns() - refresh_start) / 1_000_000
            finally:
                if overlay is not None:
                    try:
                        overlay.close()
                    except Exception:
                        pass
            
            total_elapsed = (time.perf_counter_ns() - toggle_start) / 1_000_000
            logger.info(f"[ThemeToggle] 処理時間: button={button_elapsed:.2f}ms refresh={refresh_elapsed:.2f}ms total={total_elapsed:.2f}ms")
        
        self.theme_toggle_btn.clicked.connect(on_theme_toggle)

        # NOTE:
        # Avoid connecting ThemeManager.theme_changed to a lambda that closes over
        # widget/controller objects. In long-running test suites this can leak
        # connections and keep calling into already-destroyed widgets.
        def _on_theme_changed(*_args):
            update_button_style()

        try:
            theme_manager.theme_changed.connect(_on_theme_changed)
        except Exception:
            pass

        # Ensure we disconnect when the button is destroyed.
        try:
            def _disconnect_theme_changed(*_args):
                try:
                    theme_manager.theme_changed.disconnect(_on_theme_changed)
                except Exception:
                    pass

            self.theme_toggle_btn.destroyed.connect(_disconnect_theme_changed)
        except Exception:
            pass
        
        update_button_style()
        menu_layout.addWidget(self.theme_toggle_btn)
    
    def _refresh_all_ui_colors(self):
        """全UIコンポーネントの色を再適用
        
        【最適化v2.1.7】各処理段階の時間を計測
        """
        import time
        total_start = time.perf_counter_ns()
        
        try:
            # グローバル基本スタイル適用（最初にベースレイヤー）
            # 注意: ThemeManagerで既に適用済みのため再適用をスキップ（v2.1.7 重複除去）
            global_start = time.perf_counter_ns()
            # ここでは何も適用せず、測定のみ実行
            global_elapsed = (time.perf_counter_ns() - global_start) / 1_000_000
            logger.debug("[ThemeToggle] グローバルstylesheet再適用スキップ (ThemeManager側で適用済み)")

            # 左側メニューウィジェットの背景色を更新
            menu_start = time.perf_counter_ns()
            if hasattr(self, 'menu_widget'):
                self.menu_widget.setStyleSheet(f'background-color: {get_color(ThemeKey.MENU_BACKGROUND)}; padding: 5px;')
            menu_elapsed = (time.perf_counter_ns() - menu_start) / 1_000_000
            
            # menu_area_widgetのスタイルを更新
            area_start = time.perf_counter_ns()
            try:
                from classes.theme import get_qcolor

                def _apply_widget_palette(widget, bg_key, fg_key=None, clear_style=False):
                    if widget is None:
                        return
                    if clear_style:
                        try:
                            widget.setStyleSheet("")
                        except Exception:
                            pass
                    palette = widget.palette()
                    palette.setColor(widget.backgroundRole(), get_qcolor(bg_key))
                    if fg_key is not None:
                        palette.setColor(widget.foregroundRole(), get_qcolor(fg_key))
                    widget.setAutoFillBackground(True)
                    widget.setPalette(palette)

                if hasattr(self.parent, 'menu_area_widget'):
                    _apply_widget_palette(
                        self.parent.menu_area_widget,
                        ThemeKey.WINDOW_BACKGROUND,
                        ThemeKey.WINDOW_FOREGROUND,
                        clear_style=True,
                    )

                if hasattr(self, 'menu_scroll_area'):
                    _apply_widget_palette(
                        self.menu_scroll_area,
                        ThemeKey.MENU_BACKGROUND,
                        ThemeKey.TEXT_PRIMARY,
                        clear_style=True,
                    )
                    viewport = self.menu_scroll_area.viewport() if hasattr(self.menu_scroll_area, 'viewport') else None
                    _apply_widget_palette(viewport, ThemeKey.MENU_BACKGROUND, ThemeKey.TEXT_PRIMARY, clear_style=True)
            except Exception:
                pass
            area_elapsed = (time.perf_counter_ns() - area_start) / 1_000_000
            
            # メニューボタンの再構築
            btn_start = time.perf_counter_ns()
            self._rebuild_menu_buttons_styles()
            btn_elapsed = (time.perf_counter_ns() - btn_start) / 1_000_000
            
            # テーマ切替ボタンのスタイル更新
            if hasattr(self, 'theme_toggle_btn'):
                from classes.utils.button_styles import get_button_style

                self.theme_toggle_btn.setStyleSheet(get_button_style('secondary'))
            # 閉じるボタンのスタイル更新
            if hasattr(self.parent, 'close_btn'):
                from classes.utils.button_styles import get_button_style

                self.parent.close_btn.setStyleSheet(get_button_style('danger'))
            
            # WebView周辺の背景色も更新（透過/未描画領域が黒にならないように）
            try:
                right_widget = self.parent.findChild(QWidget, 'right_widget')
                if right_widget is not None:
                    right_widget.setStyleSheet(f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};")
                webview_widget = self.parent.findChild(QWidget, 'webview_widget')
                if webview_widget is not None:
                    webview_widget.setStyleSheet(f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};")
                if hasattr(self.parent, 'webview'):
                    self.parent.webview.setStyleSheet(
                        f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};"
                    )
                    try:
                        from classes.theme import get_qcolor
                        page = self.parent.webview.page() if hasattr(self.parent.webview, 'page') else None
                        if page is not None and hasattr(page, 'setBackgroundColor'):
                            page.setBackgroundColor(get_qcolor(ThemeKey.WINDOW_BACKGROUND))
                    except Exception:
                        pass
            except Exception:
                pass
                
            # 各タブウィジェットの再描画をトリガー
            tab_start = time.perf_counter_ns()
            self._refresh_tab_widgets()
            tab_elapsed = (time.perf_counter_ns() - tab_start) / 1_000_000
            
            # メインウィンドウの再描画をトリガー
            if hasattr(self.parent, 'update'):
                self.parent.update()
            
            total_elapsed = (time.perf_counter_ns() - total_start) / 1_000_000
            logger.info(f"[ThemeToggle] _refresh_all_ui_colors: global={global_elapsed:.2f}ms menu={menu_elapsed:.2f}ms "
                       f"area={area_elapsed:.2f}ms btn={btn_elapsed:.2f}ms tab={tab_elapsed:.2f}ms total={total_elapsed:.2f}ms")
            logger.info("[ThemeToggle] UI色の再適用完了")
        except Exception as e:
            logger.error(f"[ThemeToggle] UI色再適用エラー: {e}")
    
    def _rebuild_menu_buttons_styles(self):
        """メニューボタンのスタイルを再構築（選択状態を保持）"""
        # 親ウィンドウから現在のアクティブモードを取得
        if not hasattr(self.parent, 'current_mode'):
            logger.debug("[ThemeToggle] parent.current_mode属性が存在しません")
            return
        
        current_mode = self.parent.current_mode
        if current_mode is None:
            logger.debug("[ThemeToggle] current_modeがNoneです")
            return
        
        logger.debug(f"[ThemeToggle] メニューボタンスタイル更新: current_mode={current_mode}")

        # UIController 側でメニュー配色（グループ別など）を管理している場合は、
        # それを優先して呼び出す。これによりテーマ切替直後に
        # Core の汎用inactiveスタイルで上書きされる問題を防ぐ。
        try:
            updater = getattr(self, "update_menu_button_styles", None)
            if callable(updater):
                updater(current_mode)
                return
        except Exception:
            # fallback に進む
            pass

        # Fallback: 旧ロジック（汎用スタイル）
        for mode, button in self.menu_buttons.items():
            try:
                if button is None or not hasattr(button, 'setStyleSheet'):
                    continue
                button.setStyleSheet(self._build_button_style('active' if mode == current_mode else 'inactive'))
            except (RuntimeError, AttributeError):
                continue
    
    def _refresh_tab_widgets(self):
        """各タブウィジェットの再描画
        
        【最適化v2.1.7】各タブのrefresh_theme()呼出時間を計測し、
        遅延箇所を特定してログ出力。
        """
        import time
        
        widgets = [
            ('データ取得', self.data_fetch_widget),
            ('データセット開設', self.dataset_open_widget),
            ('データ登録', self.data_register_widget),
            ('設定', self.settings_widget),
            ('データポータル', self.data_portal_widget),
        ]
        
        for name, widget in widgets:
            if widget is None:
                continue
            
            start_time = time.perf_counter_ns()
            try:
                if hasattr(widget, 'refresh_theme'):
                    widget.refresh_theme()
                else:
                    self._refresh_widget_recursive(widget)
            except Exception as e:
                logger.error(f"[ThemeToggle] {name}タブ更新エラー: {e}")
            finally:
                elapsed_ms = (time.perf_counter_ns() - start_time) / 1_000_000
                if elapsed_ms > 10:  # 10ms超過時のみログ
                    logger.warning(f"[ThemeToggle] {name}タブ更新: {elapsed_ms:.2f}ms (遅延検出)")
                else:
                    logger.debug(f"[ThemeToggle] {name}タブ更新: {elapsed_ms:.2f}ms")
    
    def _refresh_widget_recursive(self, widget):
        """ウィジェットとその子要素を再帰的に再描画
        
        【注意】テーマ切替時は配色のみ変更し、
        ファイルIO・API呼出・再構築は実行しない最適化実装。
        """
        try:
            # ウィジェット自体の更新をトリガー（再描画のみ、再構築なし）
            if hasattr(widget, 'update'):
                widget.update()
            
            # 【最適化】子要素の再帰は深さ1レベルのみに制限
            # 全階層走査を避けることでテーマ切替時の遅延を大幅削減
            # 各ウィジェットの refresh_theme() で個別対応済みのため不要
            # if hasattr(widget, 'children'):
            #     for child in widget.children():
            #         if hasattr(child, 'update'):
            #             self._refresh_widget_recursive(child)
        except Exception as e:
            logger.debug(f"[ThemeToggle] ウィジェット再描画エラー: {e}")
        
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
                    resize_main_window(self.parent, height=total_height)
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
        起動時のウィンドウ位置設定: 画面中央に配置し、タイトルバーを画面内に収める。
        v2.5.36: 初回表示時に上下左右とも画面内へクランプし、上端見切れを防止
        """
        try:
            if center_window_on_screen(self.parent):
                logger.debug("起動時ウィンドウ位置設定: 画面中央へ配置")
        except Exception as e:
            logger.error("ウィンドウ位置設定エラー: %s", e)
    
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
                '実行', 120, 36, f'background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)}; font-weight: bold; border-radius: 6px;'
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
            # 既に作成済みの場合は二重追加しない（データ取得ウィジェット二重表示対策）
            needs_image_limit = True
            existing_dropdown = getattr(self, 'image_limit_dropdown', None)
            if existing_dropdown is not None:
                try:
                    # deleted済みだと例外になる
                    _ = existing_dropdown.parent()
                    needs_image_limit = False
                except Exception:
                    needs_image_limit = True
                    self.image_limit_dropdown = None

            if needs_image_limit:
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
                    '一括実行', 120, 36, f'background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)}; font-weight: bold; border-radius: 6px;'
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
            from qt_compat.widgets import QGridLayout, QHBoxLayout, QScrollArea, QSizePolicy, QWidget, QVBoxLayout
            from qt_compat.core import Qt
            
            root_layout = QHBoxLayout()
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.setSpacing(0)

            # 左側メニュー用ウィジェット
            self.menu_widget = QWidget()
            self.menu_widget.setObjectName('left_menu_widget')
            self.menu_widget.setStyleSheet(f'background-color: {get_color(ThemeKey.MENU_BACKGROUND)}; padding: 5px;')
            self.menu_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            menu_layout = QVBoxLayout()
            menu_layout.setSpacing(8)
            menu_layout.setContentsMargins(5, 10, 5, 10)
            
            # メニューボタンを取得
            menu_buttons = self.init_mode_widgets()
            
            # ヘルプボタン以外のボタンを追加
            for button_key, button in self.menu_buttons.items():
                if button_key != 'help':
                    menu_layout.addWidget(button)
            
            # 初期モード設定
            self.parent.current_mode = "login"
            
            # 従来のメニューボタン参照を保持（互換性のため）
            self.parent.menu_btn1 = self.menu_buttons['data_fetch']
            self.parent.menu_btn2 = self.menu_buttons['dataset_open']
            self.parent.menu_btn3 = self.menu_buttons['data_register']
            self.parent.menu_btn4 = self.menu_buttons['settings']
            
            # スペースを追加（閉じるボタンとヘルプボタンを下部に配置）
            menu_layout.addStretch(1)
            
            # テーマ切替ボタンをヘルプボタンの上に配置
            self._add_theme_toggle_button(menu_layout)
            
            # ヘルプボタンを閉じるボタンの上に配置
            if 'help' in self.menu_buttons:
                menu_layout.addWidget(self.menu_buttons['help'])
            
            # 閉じるボタンを最下段に配置
            self.parent.close_btn = self.create_auto_resize_button(
                '閉じる', 120, 32, f'background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)}; font-weight: bold; border-radius: 6px; margin: 2px;'
            )
            self.parent.close_btn.clicked.connect(self.parent.close)
            menu_layout.addWidget(self.parent.close_btn)
            self.menu_widget.setLayout(menu_layout)
            self.menu_widget.setFixedWidth(140)

            self.menu_scroll_area = QScrollArea()
            self.menu_scroll_area.setObjectName('left_menu_scroll_area')
            self.menu_scroll_area.setWidgetResizable(True)
            self.menu_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.menu_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.menu_scroll_area.setFrameStyle(0)
            self.menu_scroll_area.setFixedWidth(156)
            self.menu_scroll_area.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
            self.menu_scroll_area.setStyleSheet(
                f"QScrollArea {{ background-color: {get_color(ThemeKey.MENU_BACKGROUND)}; border: none; }}"
            )
            self.menu_scroll_area.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            try:
                self.menu_scroll_area.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                self.menu_scroll_area.viewport().setStyleSheet(
                    f"background-color: {get_color(ThemeKey.MENU_BACKGROUND)};"
                )
            except Exception:
                pass
            self.menu_scroll_area.setWidget(self.menu_widget)

            # 右側：上（WebView）・下（個別メニュー）に分割
            right_widget = QWidget()
            right_widget.setObjectName('right_widget')
            right_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            right_widget.setStyleSheet(
                f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.WINDOW_FOREGROUND)};"
            )
            right_main_layout = QVBoxLayout()
            right_main_layout.setSpacing(5)
            right_main_layout.setContentsMargins(5, 5, 5, 5)
            
            # 上部：WebView + 待機メッセージ専用エリア
            webview_widget = QWidget()
            webview_widget.setObjectName('webview_widget')
            webview_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            webview_widget.setStyleSheet(
                f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.WINDOW_FOREGROUND)};"
            )
            # 初期サイズを設定してネガティブサイズエラーを防止
            webview_widget.setMinimumSize(100, 50)
            # 初期ロード時にグローバルスタイル適用（右側コンテナ生成直後）
            try:
                from qt_compat.widgets import QApplication
            except Exception:
                QApplication = None  # type: ignore
            app = QApplication.instance() if QApplication else None
            if app is not None:
                app.setStyleSheet(get_global_base_style())
            
            # WebViewレイアウト（WebView + ログインコントロール）
            # WebView領域を右端まで広げ、ログインコントロールは上に重ねる。
            webview_layout = QGridLayout()
            webview_layout.setContentsMargins(0, 0, 0, 0)
            webview_layout.setSpacing(0)
            # WebViewの背景が透過指定されても下地が黒くならないよう、
            # コンテナ側の背景色を明示しておく（WebView自身にも念のため適用）。
            try:
                self.parent.webview.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};"
                )

                # QWebEnginePage側の背景色も明示（ページの未描画領域/透過で黒が出る対策）
                try:
                    from classes.theme import get_qcolor
                    page = self.parent.webview.page() if hasattr(self.parent.webview, 'page') else None
                    if page is not None and hasattr(page, 'setBackgroundColor'):
                        page.setBackgroundColor(get_qcolor(ThemeKey.WINDOW_BACKGROUND))
                except Exception:
                    pass
            except Exception:
                pass
            webview_layout.addWidget(self.parent.webview, 0, 0)
            
            # ログインコントロールウィジェットを追加
            try:
                from classes.login.ui.login_control_widget import create_login_control_widget
                self.parent.login_control_widget = create_login_control_widget(
                    self.parent, 
                    self.parent.webview
                )
                self.parent.login_control_widget.setMaximumWidth(300)
                from qt_compat.core import Qt
                webview_layout.addWidget(
                    self.parent.login_control_widget,
                    0,
                    0,
                    alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                )
                try:
                    self.parent.login_control_widget.raise_()
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"ログインコントロールウィジェット初期化エラー: {e}")
                # エラー時はスペーサーで代替
                try:
                    # QGridLayoutにはaddSpacingが無い
                    webview_layout.setRowMinimumHeight(0, 1)
                except Exception:
                    pass
            
            # v2.0.2: 待機メッセージ専用エリア（WebView直下に配置）
            vbox = QVBoxLayout()
            vbox.setSpacing(5)
            vbox.addLayout(webview_layout)
            
            # 待機メッセージ用の専用フレーム
            message_frame = QWidget()
            message_frame.setStyleSheet(f'''
                QWidget {{
                    background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                    border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                    border-radius: 4px;
                    margin: 5px 0px;
                }}
            ''')
            message_layout = QVBoxLayout()
            message_layout.setContentsMargins(10, 5, 10, 5)
            message_layout.setSpacing(3)
            
            # 待機メッセージラベル（目立つ位置）
            message_layout.addWidget(self.parent.autologin_msg_label)
            message_layout.addWidget(self.parent.webview_msg_label)
            
            # v2.1.3: ログイン処理説明ラベル（WebView下部に配置）
            if hasattr(self.parent, 'login_help_label'):
                message_layout.addWidget(self.parent.login_help_label)
            
            message_frame.setLayout(message_layout)
            vbox.addWidget(message_frame)
            
            webview_widget.setLayout(vbox)
            
            # 下部：個別メニュー（切り替え可能エリア）
            self.parent.menu_area_widget = QWidget()
            self.parent.menu_area_widget.setObjectName('menu_area_widget')
            self.parent.menu_area_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.parent.menu_area_widget.setStyleSheet(f"""
                #menu_area_widget {{
                    background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};
                    color: {get_color(ThemeKey.WINDOW_FOREGROUND)};
                }}
                #menu_area_widget QLabel {{
                    color: {get_color(ThemeKey.WINDOW_FOREGROUND)};
                }}
            """)
            self.parent.menu_area_layout = QVBoxLayout()
            self.parent.menu_area_layout.setContentsMargins(5, 5, 5, 5)
            self.parent.menu_area_widget.setLayout(self.parent.menu_area_layout)
            
            # 右側全体に追加
            right_main_layout.addWidget(webview_widget, 3)
            right_main_layout.addWidget(self.parent.menu_area_widget, 1)

            # 外部アクセスモニターバー（最下部）
            try:
                from classes.ui.external_access_monitor_widget import ExternalAccessMonitorBar
                self.parent.external_access_monitor_bar = ExternalAccessMonitorBar(self.parent)
                right_main_layout.addWidget(self.parent.external_access_monitor_bar, 0)
            except Exception as e:
                logger.debug("外部アクセスモニターバー初期化スキップ: %s", e)

            right_widget.setLayout(right_main_layout)

            # ルートレイアウトに左右追加
            root_layout.addWidget(self.menu_scroll_area)
            root_layout.addWidget(right_widget, 1)
            self.parent.setLayout(root_layout)
            set_main_window_minimum_size(self.parent)

            # 現象解析用: 起動直後の背景/geometryを一度だけダンプ
            try:
                from qt_compat.core import QTimer
                QTimer.singleShot(0, self._debug_dump_webview_area)
            except Exception:
                pass
            
            # タブ統合機能を追加
            # 既定ではタブ統合は無効（意図しない追加ウィンドウ/レイアウト崩れを避ける）
            if self._should_enable_tab_integrator():
                self._integrate_settings_tab()
            else:
                logger.debug("タブ統合機能は無効化されています (app.enable_tab_integrator=false)")
            
        except Exception as e:
            logger.error("メインレイアウト設定エラー: %s", e)

    def _debug_dump_webview_area(self):
        """黒帯/余白の原因特定用に、主要ウィジェットの状態をDEBUGログへ出力"""
        try:
            from qt_compat.widgets import QWidget
        except Exception:
            return

        def dump_widget(label: str, w: QWidget | None):
            if w is None:
                logger.info("[UIDump] %s: None", label)
                return
            try:
                ss = w.styleSheet() if hasattr(w, 'styleSheet') else ''
            except Exception:
                ss = ''
            try:
                pal = w.palette() if hasattr(w, 'palette') else None
                bg = pal.color(pal.Window).name() if pal is not None else None
            except Exception:
                bg = None
            try:
                logger.info(
                    "[UIDump] %s: cls=%s obj=%s vis=%s geom=%s min=%s max=%s sizePolicy=%s bg=%s ss_len=%s",
                    label,
                    type(w).__name__,
                    w.objectName() if hasattr(w, 'objectName') else None,
                    w.isVisible() if hasattr(w, 'isVisible') else None,
                    w.geometry() if hasattr(w, 'geometry') else None,
                    w.minimumSize() if hasattr(w, 'minimumSize') else None,
                    w.maximumSize() if hasattr(w, 'maximumSize') else None,
                    w.sizePolicy() if hasattr(w, 'sizePolicy') else None,
                    bg,
                    len(ss) if ss is not None else 0,
                )
            except Exception:
                pass

        try:
            dump_widget('parent', self.parent)
            dump_widget('right_widget', self.parent.findChild(QWidget, 'right_widget'))
            dump_widget('webview_widget', self.parent.findChild(QWidget, 'webview_widget'))
            dump_widget('webview', getattr(self.parent, 'webview', None))
            dump_widget('login_control_widget', getattr(self.parent, 'login_control_widget', None))
        except Exception:
            pass
            
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

    def _should_enable_tab_integrator(self) -> bool:
        """タブ統合機能を有効にするか判定する。

        既定: False
        有効化: config の app.enable_tab_integrator = true
        """
        try:
            cfg = getattr(self.parent, 'config_manager', None)
            if cfg is None:
                return False
            return bool(cfg.get('app.enable_tab_integrator', False))
        except Exception:
            return False
    
    def finalize_window_setup(self):
        """
        ウィンドウの表示と最終設定
        """
        try:
            import os
            from config.common import DEBUG_INFO_FILE, LOGIN_FILE
            
            self.parent.show()
            fit_main_window_height_to_screen(self.parent)
            self.center_window()

            try:
                self.parent._initial_window_client_width = int(self.parent.width())
                self.parent._initial_window_client_height = int(self.parent.height())
            except Exception:
                pass

            current_min_width = 200
            try:
                current_min_width = max(200, int(self.parent.minimumWidth()))
            except Exception:
                pass
            set_main_window_minimum_size(self.parent, min_width=current_min_width)

            # login.txtのパス情報をinfo.txtに出力（ユーザーディレクトリ配下）
            info_path = DEBUG_INFO_FILE
            login_path = LOGIN_FILE
            login_info = f"login.txt path : {os.path.abspath(login_path)}"

            try:
                os.makedirs(os.path.dirname(info_path), exist_ok=True)
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
