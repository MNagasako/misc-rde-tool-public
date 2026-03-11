"""
イベントハンドラークラス - ARIM RDE Tool
Browserクラスから イベント処理ロジックを分離
リサイズイベント・フォント再調整・安全性向上対応
【注意】バージョン更新時はconfig/common.py のREVISIONも要確認
"""
import logging
from qt_compat.core import QEvent, Qt, QTimer
from qt_compat.widgets import QWidget

logger = logging.getLogger(__name__)

class EventHandler:
    """イベント処理を担当するクラス"""
    
    def __init__(self, parent_widget):
        """
        イベントハンドラーの初期化
        Args:
            parent_widget: 親ウィジェット（Browserクラスのインスタンス）
        """
        self.parent = parent_widget
        self._fixed_aspect_ratio = None
        self.auto_close = False
        self.closed = False
        
    def set_auto_close(self, auto_close):
        """
        自動クローズフラグを設定
        Args:
            auto_close: 自動クローズフラグ
        """
        self.auto_close = auto_close
        
    def set_fixed_aspect_ratio(self, ratio):
        """
        固定アスペクト比を設定
        Args:
            ratio: アスペクト比（幅/高さ）
        """
        self._fixed_aspect_ratio = ratio
        
    def handle_resize_event(self, event):
        """
        リサイズイベントを処理
        Args:
            event: リサイズイベント
        """
        # オーバーレイマネージャーがある場合、位置を更新
        if hasattr(self.parent, 'overlay_manager') and self.parent.overlay_manager:
            self.parent.overlay_manager.resize_overlay()
            
        # リサイズ後にメニューボタンのフォントサイズを再調整
        if hasattr(self.parent, 'ui_controller') and self.parent.ui_controller:
            from qt_compat.core import QTimer
            # 少し遅延させて確実にリサイズ後のサイズでフォント調整
            QTimer.singleShot(100, self._adjust_all_menu_fonts)
    
    def _adjust_all_menu_fonts(self):
        """
        すべてのメニューボタンのフォントサイズを再調整（安全性チェック付き）
        """
        try:
            ui_controller = self.parent.ui_controller
            # メニューボタンのフォントサイズを再調整
            for button in ui_controller.menu_buttons.values():
                try:
                    if button is not None and hasattr(button, 'isVisible') and button.isVisible():
                        ui_controller.adjust_button_font_size(button)
                except (RuntimeError, AttributeError):
                    # オブジェクトが削除済みまたは属性がない場合は無視
                    continue
            
            # 閉じるボタンのフォントサイズも再調整
            if hasattr(self.parent, 'close_btn') and self.parent.close_btn:
                try:
                    if hasattr(self.parent.close_btn, 'isVisible') and self.parent.close_btn.isVisible():
                        ui_controller.adjust_button_font_size(self.parent.close_btn)
                except (RuntimeError, AttributeError):
                    pass
                
            # その他のボタンも再調整
            if hasattr(self.parent, 'grant_btn') and self.parent.grant_btn:
                try:
                    if hasattr(self.parent.grant_btn, 'isVisible') and self.parent.grant_btn.isVisible():
                        ui_controller.adjust_button_font_size(self.parent.grant_btn)
                except (RuntimeError, AttributeError):
                    pass
            if hasattr(self.parent, 'batch_btn') and self.parent.batch_btn:
                try:
                    if hasattr(self.parent.batch_btn, 'isVisible') and self.parent.batch_btn.isVisible():
                        ui_controller.adjust_button_font_size(self.parent.batch_btn)
                except (RuntimeError, AttributeError):
                    pass
        except Exception as e:
            logger.warning(f"メニューフォント再調整中にエラー: {e}")
                
    def handle_event_filter(self, obj, event):
        """
        イベントフィルターを処理
        Args:
            obj: イベントの対象オブジェクト
            event: イベント
        Returns:
            bool: イベントが処理された場合True、そうでなければFalse
        """
        # マウスクリックイベントの処理
        if event.type() == QEvent.MouseButtonPress:
            # 左クリックの場合
            if event.button() == Qt.LeftButton:
                # オーバーレイが表示されている場合は非表示にする
                if hasattr(self.parent, 'overlay_manager') and self.parent.overlay_manager:
                    if self.parent.overlay_manager.is_overlay_visible():
                        self.parent.overlay_manager.hide_overlay()
                        return True  # イベントを処理済みとして返す
                        
        # その他のイベントは標準処理に委譲
        return False
        
    def handle_url_changed(self, url):
        """
        URL変更イベントを処理
        Args:
            url: 変更後のURL
        """
        url_str = url.toString()
        
        # URLをログに記録
        if hasattr(self.parent, 'url_list'):
            self.parent.url_list.append(url_str)
            
        # 親ウィジェットのメッセージを更新
        if hasattr(self.parent, 'display_manager'):
            self.parent.display_manager.set_message(f"URL変更: {url_str}")
            
        # ログイン状態の確認
        if hasattr(self.parent, 'login_manager'):
            self.parent.login_manager.check_login_status(url_str)
            
        logger.debug("URL変更: %s", url_str)
        
    def handle_load_finished(self, success):
        """
        ページロード完了イベントを処理
        Args:
            success: ロードが成功した場合True
        """
        if success:
            message = "ページロードが完了しました"
            if hasattr(self.parent, 'display_manager'):
                self.parent.display_manager.set_message(message)
                
            # ログイン状態の確認
            if hasattr(self.parent, 'login_manager'):
                self.parent.login_manager.check_page_load_status()
                
            print(message)
        else:
            message = "ページロードに失敗しました"
            if hasattr(self.parent, 'display_manager'):
                self.parent.display_manager.set_message(message)
            print(message)
            
    def get_event_statistics(self):
        """
        イベント統計情報を取得
        Returns:
            dict: 統計情報
        """
        stats = {
            'url_changes': len(self.parent.url_list) if hasattr(self.parent, 'url_list') else 0,
            'fixed_aspect_ratio': self._fixed_aspect_ratio
        }
        return stats
    
    def setup_connections(self):
        """
        シグナル/スロット接続の設定
        """
        # WebViewイベント接続
        if hasattr(self.parent, 'webview'):
            self.parent.webview.page().loadFinished.connect(self.on_load_finished)
            try:
                self.parent.webview.loadStarted.connect(self.on_load_started)
            except Exception:
                pass
            self.parent.webview.urlChanged.connect(self.on_url_changed)
        
        # Cookieイベント接続
        if hasattr(self.parent, 'login_manager'):
            self.parent.webview.page().profile().cookieStore().cookieAdded.connect(
                self.parent.login_manager.on_cookie_added
            )
        
        # ボタンイベント接続
        self._setup_button_connections()
    
    def _setup_button_connections(self):
        """
        ボタンのクリックイベント接続
        """
        # メニューボタン接続
        if hasattr(self.parent, 'menu_btn4'):
            self.parent.menu_btn4.clicked.connect(lambda: self.parent.switch_mode("settings"))
        if hasattr(self.parent, 'menu_btn5'):
            self.parent.menu_btn5.clicked.connect(lambda: self.parent.switch_mode("tools"))
        if hasattr(self.parent, 'menu_btn6'):
            self.parent.menu_btn6.clicked.connect(lambda: self.parent.switch_mode("logs"))
        if hasattr(self.parent, 'menu_btn7'):
            self.parent.menu_btn7.clicked.connect(lambda: self.parent.switch_mode("extras"))
        
        # 閉じるボタン接続
        if hasattr(self.parent, 'close_btn'):
            self.parent.close_btn.clicked.connect(self.parent.close)
        
        # グラント番号ボタン接続
        if hasattr(self.parent, 'grant_btn'):
            self.parent.grant_btn.clicked.connect(self.parent.on_grant_number_decided)
        
        # バッチ実行ボタン接続
        if hasattr(self.parent, 'batch_btn'):
            self.parent.batch_btn.clicked.connect(self.parent.execute_batch_grant_numbers)
    
    def on_load_finished(self, ok):
        """
        ページロード完了イベント処理
        Args:
            ok: ロード成功フラグ
        """
        if ok:
            logger.info("ページのロードが完了しました。Cookieを取得します。")
            self.parent.webview.page().profile().cookieStore().loadAllCookies()
            self.parent.log_webview_html(self.parent.webview.url())  # ロード完了時にもHTML保存
            
            # 横スクロールバーが出ないようにズーム調整
            def adjust_zoom():
                view_width = self.parent.webview.width()
                try:
                    # js_templatesのインポートを動的に行う
                    from functions.common_funcs import load_js_template
                    js_code = load_js_template('adjust_zoom.js')
                except ImportError:
                    # インポートに失敗した場合はデフォルトのJSコード
                    js_code = "document.body.scrollWidth;"
                
                def set_zoom(page_width):
                    try:
                        if page_width and view_width > 0 and page_width > view_width:
                            zoom = view_width / page_width
                            zoom = max(0.3, min(zoom, 1.0))
                            logger.info(f"[INFO] 横幅調整: page_width={page_width}, view_width={view_width}, zoom={zoom}")
                            self.parent.webview.setZoomFactor(zoom)
                        else:
                            self.parent.webview.setZoomFactor(1.0)
                    except Exception as e:
                        logger.warning(f"ズーム調整失敗: {e}")
                
                self.parent.webview.page().runJavaScript(js_code, set_zoom)
            
            QTimer.singleShot(500, adjust_zoom)
            
            # 自動クローズが有効な場合のみタイマーを設定
            if self.auto_close:
                from qt_compat.widgets import QApplication
                QTimer.singleShot(1000, lambda: QApplication.quit())

        def on_load_started(self):
            """ページロード開始時の処理。

            環境によっては遷移中にQWebEngineViewが黒くクリアされるため、
            loadStartedのタイミングでも背景色を明示しておく。
            """
            try:
                from classes.theme import get_qcolor, ThemeKey

                # WebView周辺の下地（未描画領域が黒にならないように）
                try:
                    right_widget = self.parent.findChild(QWidget, 'right_widget')
                    if right_widget is not None:
                        # 固定色を当てるとテーマ切替後に残留するため、palette参照にする
                        right_widget.setStyleSheet("background-color: palette(window);")
                except Exception:
                    pass
                try:
                    webview_widget = self.parent.findChild(QWidget, 'webview_widget')
                    if webview_widget is not None:
                        webview_widget.setStyleSheet("background-color: palette(window);")
                except Exception:
                    pass

                # WebView自身
                try:
                    if hasattr(self.parent, 'webview'):
                        self.parent.webview.setStyleSheet("background-color: palette(window);")
                        page = self.parent.webview.page() if hasattr(self.parent.webview, 'page') else None
                        if page is not None and hasattr(page, 'setBackgroundColor'):
                            page.setBackgroundColor(get_qcolor(ThemeKey.WINDOW_BACKGROUND))
                except Exception:
                    pass
            except Exception:
                return
    
    def on_url_changed(self, url):
        """
        URL変更イベント処理
        Args:
            url: 新しいURL
        """
        # v1.20.3: URL変更の詳細ログ
        url_str = url.toString()
        logger.info(f"[URL] ━━━ URL変更: {url_str}")
        
        # ホスト判定
        if "rde-material.nims.go.jp" in url_str:
            logger.info("[URL] 📍 rde-material.nims.go.jp に遷移")
        elif "rde.nims.go.jp" in url_str:
            logger.info("[URL] 📍 rde.nims.go.jp に遷移")
        elif "diceidm.nims.go.jp" in url_str:
            logger.info("[URL] 📍 diceidm.nims.go.jp (DICE認証)")
        elif "dicelogin.b2clogin.com" in url_str:
            logger.info("[URL] 📍 dicelogin.b2clogin.com (Azure AD B2C)")
        
        # エラーページ検出（OAuth2認証フロー中の一時的なエラーページは正常）
        if "401" in url_str or "error" in url_str.lower():
            # ホスト判定
            if "rde-material.nims.go.jp" in url_str:
                # Material APIのOAuth2認証フロー中は一時的に/errorにリダイレクトされる（正常動作）
                logger.debug(f"[URL] ℹ️ Material API認証フロー: {url_str}")
            elif "rde.nims.go.jp" in url_str:
                logger.warning(f"[URL] ⚠️ エラーページ検出: {url_str}")
                logger.error("[URL] ❌ rde.nims.go.jp で401エラー")
            else:
                logger.warning(f"[URL] ⚠️ エラーページ検出: {url_str}")
                logger.error(f"[URL] ❌ 不明なホストで401エラー: {url_str}")
        
        # URL変更時にHTMLを保存＆URLリスト記録
        self.parent.log_webview_html(url)
        
        # 自動判定: /rde/datasets に到達したら自動でクッキー保存＆終了
        # 手動クローズモード（デフォルト）では自動的にフォーム表示
        if not self.auto_close and not self.closed:
            if '/rde/datasets' in url.toString():
                # v1.18.4: 初回到達時のみ処理実行（Material URL遷移後の戻り時に再実行を防ぐ）
                if not hasattr(self.parent.login_manager, '_initial_datasets_reached'):
                    logger.info('[LOGIN] ✅ RDEデータセットページに到達 - Cookieとトークンを保存します')
                    self.parent.show_overlay()
                    
                    # 初回到達フラグを設定
                    self.parent.login_manager._initial_datasets_reached = True
                    
                    # v1.20.3: PySide6対応 - sessionStorage設定待機のため3秒遅延
                    logger.info('[TOKEN] Bearerトークン自動取得を開始（3秒後）')
                    # v2.1.x: ensure_both_tokensを使用して順次取得（RDE -> Material）
                    self.parent.login_manager.ensure_both_tokens()
                    
                    # Cookie保存とフォーム表示
                    QTimer.singleShot(1000, self.parent.save_cookies_and_show_grant_form)
                else:
                    logger.info('[LOGIN] RDEデータセットページに戻りましたが、トークン取得は既に実行済み（スキップ）')
    
    def handle_close_event(self, event):
        """
        クローズイベント処理
        Args:
            event: クローズイベント
        """
        # アプリケーション終了時の処理
        event.accept()
    
    def set_closed(self, closed):
        """
        クローズ済みフラグの設定
        Args:
            closed: クローズ済みフラグ
        """
        self.closed = closed
