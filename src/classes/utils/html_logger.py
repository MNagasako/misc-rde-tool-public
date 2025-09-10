"""
HTML出力とログ処理を担当するクラス - ARIM RDE Tool v1.13.1
Browserクラスからログ・HTML保存ロジックを分離
WebView HTML保存・URL追跡・ログ管理機能
【注意】バージョン更新時はconfig/common.py のREVISIONも要確認
"""
import os
import logging
from config.common import WEBVIEW_HTML_DIR, WEBVIEW_URL_LOG_FILE, WEBVIEW_HTML_MAP_FILE

logger = logging.getLogger(__name__)

class HtmlLogger:
    """HTML出力とログ処理を担当するクラス"""
    
    def __init__(self):
        """
        HtmlLoggerの初期化
        """
        self.html_count = 0
        self.url_list = []
        
        # 必要なディレクトリを作成
        if not os.path.exists(WEBVIEW_HTML_DIR):
            os.makedirs(WEBVIEW_HTML_DIR, exist_ok=True)
    
    def log_webview_html(self, webview, url=None):
        """
        WebViewのHTMLをファイルに保存
        Args:
            webview: QWebEngineView インスタンス
            url: 現在のURL（Qurl型またはNone）
        """
        def save_html(html):
            # ファイル名生成
            fname = f"{self.html_count:03d}.html"
            fpath = os.path.join(WEBVIEW_HTML_DIR, fname)
            
            # HTMLファイルを保存
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(html)
            
            # URLリストにも記録
            if url:
                url_str = url.toString() if hasattr(url, 'toString') else str(url)
                self.url_list.append((fname, url_str))
                
                # URLログファイルに追記
                with open(WEBVIEW_URL_LOG_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{fname}\t{url_str}\n")
                
                # マッピングファイルにも追記
                with open(WEBVIEW_HTML_MAP_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{fname}\t{url_str}\n")
            
            self.html_count += 1
            logger.debug(f"HTML保存完了: {fname}")
        
        webview.page().toHtml(save_html)
    
    def get_html_count(self):
        """
        保存されたHTMLファイルの数を取得
        Returns:
            int: HTMLファイル数
        """
        return self.html_count
    
    def get_url_list(self):
        """
        記録されたURLリストを取得
        Returns:
            list: (filename, url) のタプルのリスト
        """
        return self.url_list.copy()
    
    def clear_logs(self):
        """
        ログ情報をクリア
        """
        self.html_count = 0
        self.url_list.clear()
        logger.info("HTMLログ情報をクリアしました")
