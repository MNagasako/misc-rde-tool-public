"""
BrowserControllerクラス - ARIM RDE Tool v1.13.1
Browserクラスからブラウザ制御ロジックを分離
WebView管理・URL変更・ページナビゲーション・JavaScript実行機能
【注意】バージョン更新時はconfig/common.py のREVISIONも要確認
"""

import os
import logging
from PyQt5.QtCore import QTimer, QUrl
from PyQt5.QtWebEngineWidgets import QWebEngineView
from config.common import get_dynamic_file_path
from config.site_rde import URLS
from functions.common_funcs import load_js_template
from classes.utils.debug_log import debug_log

logger = logging.getLogger(__name__)

class BrowserController:
    """ブラウザ制御機能を管理するクラス"""
    
    def __init__(self, parent_widget):
        """
        BrowserControllerの初期化
        
        Args:
            parent_widget: 親ウィジェット（Browserクラスのインスタンス）
        """
        self.parent = parent_widget
        self.logger = logging.getLogger("BrowserController")
        
        # ブラウザ関連の状態変数
        self._webview_fixed_width = 900
        
        self.logger.info("BrowserController初期化完了")
    
    @debug_log
    def setup_webview(self, webview):
        """
        WebViewの初期設定を行う
        
        Args:
            webview: QWebEngineViewインスタンス
        """
        # WebViewサイズ設定
        webview.setFixedHeight(500)
        webview.setFixedWidth(self._webview_fixed_width)
        
        # URL読み込み
        webview.load(QUrl(URLS["web"]["base"]))
        
        # イベント接続
        webview.loadFinished.connect(self.on_load_finished)
        webview.urlChanged.connect(self.on_url_changed)
        
        self.logger.info("WebView設定完了")
    
    @debug_log
    def on_load_finished(self, ok):
        """
        ページロード完了時の処理
        
        Args:
            ok: ロード成功フラグ
        """
        if ok:
            self.logger.info("ページのロードが完了しました。Cookieを取得します。")
            
            # Cookie取得
            self.parent.webview.page().profile().cookieStore().loadAllCookies()
            
            # HTML保存処理
            self.parent.log_webview_html(self.parent.webview.url())
            
            # ズーム調整処理
            self._adjust_zoom()
            
            # ログイン完了判定処理
            self._check_login_completion()
            
            # 自動クローズ処理
            if self.parent.auto_close:
                QTimer.singleShot(1000, self.parent.close)
        else:
            self.logger.warning("ページのロードに失敗しました。")
    
    @debug_log
    def on_url_changed(self, url):
        """
        URL変更時の処理
        
        Args:
            url: 新しいURL
        """
        # EventHandlerに処理を委譲
        if hasattr(self.parent, 'event_handler'):
            self.parent.event_handler.on_url_changed(url)
    
    @debug_log
    def _adjust_zoom(self):
        """横スクロールバーが出ないようにズーム調整"""
        view_width = self.parent.webview.width()
        js_code = load_js_template('adjust_zoom.js')
        
        def set_zoom(page_width):
            try:
                if page_width and view_width > 0 and page_width > view_width:
                    zoom = view_width / page_width
                    zoom = max(0.3, min(zoom, 1.0))
                    self.logger.info(f"横幅調整: page_width={page_width}, view_width={view_width}, zoom={zoom}")
                    self.parent.webview.setZoomFactor(zoom)
                else:
                    self.parent.webview.setZoomFactor(1.0)
            except Exception as e:
                self.logger.warning(f"ズーム調整失敗: {e}")
        
        # 500ms後にズーム調整実行
        QTimer.singleShot(500, lambda: self.parent.webview.page().runJavaScript(js_code, set_zoom))
    
    @debug_log
    def _check_login_completion(self):
        """ログイン完了判定とUI更新"""
        try:
            url = self.parent.webview.url().toString()
            if self.is_rde_logged_in_url(url):
                if hasattr(self.parent, 'ui_controller') and hasattr(self.parent.ui_controller, 'on_webview_login_success'):
                    # ログイン成功時のUI更新処理
                    pass
                    # self.parent.ui_controller.on_webview_login_success()
        except Exception as e:
            self.logger.debug(f"ログイン完了判定エラー: {e}")
    
    @debug_log
    def is_rde_logged_in_url(self, url):
        """
        RDEログイン完了後の画面かどうかを判定
        
        Args:
            url: 判定対象URL
            
        Returns:
            bool: ログイン完了後の画面の場合True
        """
        if not url:
            return False
        
        url = url.lower()
        
        # ログイン画面や認証ページでないことを厳密に判定
        if "login" in url or "signin" in url or "auth" in url:
            return False
        
        # RDEのメイン画面URLパターン
        if "rde.nims.go.jp" in url or "rde-entry" in url:
            return True
        
        return False
    
    @debug_log
    def execute_javascript(self, script, callback=None):
        """
        JavaScript実行の統一インターフェース
        
        Args:
            script: 実行するJavaScriptコード
            callback: 実行結果を受け取るコールバック関数
        """
        try:
            self.parent.webview.page().runJavaScript(script, callback)
            self.logger.debug(f"JavaScript実行: {script[:100]}...")
        except Exception as e:
            self.logger.error(f"JavaScript実行エラー: {e}")
    
    @debug_log
    def load_url(self, url):
        """
        指定URLをWebViewに読み込む
        
        Args:
            url: 読み込み対象URL
        """
        try:
            self.parent.webview.load(QUrl(url))
            self.logger.info(f"URL読み込み: {url}")
        except Exception as e:
            self.logger.error(f"URL読み込みエラー: {e}")
    
    @debug_log
    def get_current_url(self):
        """
        現在のURLを取得
        
        Returns:
            str: 現在のURL
        """
        try:
            return self.parent.webview.url().toString()
        except Exception as e:
            self.logger.error(f"URL取得エラー: {e}")
            return ""
    
    @debug_log
    def set_zoom_factor(self, factor):
        """
        WebViewのズームファクターを設定
        
        Args:
            factor: ズームファクター（0.25-5.0）
        """
        try:
            factor = max(0.25, min(factor, 5.0))  # 範囲制限
            self.parent.webview.setZoomFactor(factor)
            self.logger.info(f"ズームファクター設定: {factor}")
        except Exception as e:
            self.logger.error(f"ズームファクター設定エラー: {e}")
    
    @debug_log
    def reload_page(self):
        """ページを再読み込み"""
        try:
            self.parent.webview.reload()
            self.logger.info("ページ再読み込み実行")
        except Exception as e:
            self.logger.error(f"ページ再読み込みエラー: {e}")
    
    @debug_log
    def go_back(self):
        """ブラウザの戻る機能"""
        try:
            self.parent.webview.back()
            self.logger.info("ブラウザ戻る実行")
        except Exception as e:
            self.logger.error(f"ブラウザ戻るエラー: {e}")
    
    @debug_log
    def go_forward(self):
        """ブラウザの進む機能"""
        try:
            self.parent.webview.forward()
            self.logger.info("ブラウザ進む実行")
        except Exception as e:
            self.logger.error(f"ブラウザ進むエラー: {e}")
