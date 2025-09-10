"""
ローカルプロキシサーバー（テスト用）

HTTPプロキシとして動作し、リクエストを転送
チェックポイントテストでの動作確認用
"""

import http.server
import socketserver
import urllib.request
import urllib.parse
import urllib.error
import threading
import time
import sys
from typing import Optional, Dict, Any


class ProxyHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """プロキシHTTPリクエストハンドラー"""
    
    def do_GET(self):
        """GET リクエストの処理"""
        self._handle_request()
    
    def do_POST(self):
        """POST リクエストの処理"""
        self._handle_request()
    
    def do_PUT(self):
        """PUT リクエストの処理"""
        self._handle_request()
    
    def do_DELETE(self):
        """DELETE リクエストの処理"""
        self._handle_request()
    
    def do_CONNECT(self):
        """CONNECT リクエストの処理（HTTPS用）"""
        # 簡易実装：CONNECTは成功レスポンスのみ
        self.send_response(200, 'Connection established')
        self.end_headers()
        
        # ログ記録
        print(f"[PROXY] CONNECT {self.path}")
    
    def _handle_request(self):
        """共通リクエスト処理"""
        try:
            # リクエストURL構築
            if self.path.startswith('http'):
                url = self.path
            else:
                # 相対パスの場合はHostヘッダーから構築
                host = self.headers.get('Host', 'localhost')
                protocol = 'https' if self.server.server_port == 443 else 'http'
                url = f"{protocol}://{host}{self.path}"
            
            # リクエストヘッダー取得
            headers = {}
            for key, value in self.headers.items():
                if key.lower() not in ['host', 'connection']:
                    headers[key] = value
            
            # リクエストボディ取得
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length) if content_length > 0 else None
            
            # 実際のリクエスト実行
            req = urllib.request.Request(url, data=post_data, headers=headers, method=self.command)
            
            with urllib.request.urlopen(req, timeout=30) as response:
                # レスポンスステータス
                self.send_response(response.status)
                
                # レスポンスヘッダー
                for key, value in response.headers.items():
                    if key.lower() not in ['connection', 'transfer-encoding']:
                        self.send_header(key, value)
                self.end_headers()
                
                # レスポンスボディ
                self.wfile.write(response.read())
            
            # ログ記録
            print(f"[PROXY] {self.command} {url} -> {response.status}")
            
        except Exception as e:
            # エラーレスポンス
            self.send_error(502, f"Proxy Error: {str(e)}")
            print(f"[PROXY] ERROR {self.command} {self.path}: {e}")
    
    def log_message(self, format, *args):
        """ログメッセージ（標準出力への出力を制御）"""
        # 詳細ログは無効化（必要に応じてコメントアウト）
        pass


class LocalProxyServer:
    """ローカルプロキシサーバー管理"""
    
    def __init__(self, port: int = 8888):
        self.port = port
        self.server: Optional[socketserver.TCPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
    
    def start(self) -> bool:
        """プロキシサーバー開始"""
        try:
            self.server = socketserver.TCPServer(("127.0.0.1", self.port), ProxyHTTPRequestHandler)
            self.server.allow_reuse_address = True
            
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            
            self.running = True
            print(f"✅ ローカルプロキシサーバー開始: http://127.0.0.1:{self.port}")
            
            # 起動確認
            time.sleep(0.5)
            return True
            
        except Exception as e:
            print(f"❌ プロキシサーバー開始失敗: {e}")
            return False
    
    def stop(self) -> None:
        """プロキシサーバー停止"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.running = False
            print(f"✅ ローカルプロキシサーバー停止: port {self.port}")
    
    def is_running(self) -> bool:
        """動作状況確認"""
        return self.running and self.thread is not None and self.thread.is_alive()
    
    def get_proxy_url(self) -> str:
        """プロキシURLを取得"""
        return f"http://127.0.0.1:{self.port}"


def main():
    """メイン実行（サーバー単体起動用）"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ローカルHTTPプロキシサーバー")
    parser.add_argument("--port", type=int, default=8888, help="プロキシポート番号")
    parser.add_argument("--duration", type=int, default=0, help="実行時間（秒、0=無制限）")
    
    args = parser.parse_args()
    
    proxy = LocalProxyServer(port=args.port)
    
    if proxy.start():
        try:
            if args.duration > 0:
                print(f"⏰ {args.duration}秒間実行後に自動停止")
                time.sleep(args.duration)
            else:
                print("🔄 Ctrl+C で停止")
                while True:
                    time.sleep(1)
        except KeyboardInterrupt:
            print("\n⏹️ 停止中...")
        finally:
            proxy.stop()
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
