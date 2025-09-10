"""
PACファイル配布サーバー（テスト用）

Proxy Auto-Configuration (PAC) ファイルをHTTPで配布
チェックポイントテストでの動作確認用
"""

import http.server
import socketserver
import threading
import time
import sys
from typing import Optional


# デフォルトPACファイル内容
DEFAULT_PAC_CONTENT = """
function FindProxyForURL(url, host) {
    // ローカル・プライベート・ループバックアドレスは直接接続
    if (isPlainHostName(host) ||
        shExpMatch(host, "localhost*") ||
        isInNet(dnsResolve(host), "10.0.0.0", "255.0.0.0") ||
        isInNet(dnsResolve(host), "172.16.0.0", "255.240.0.0") ||
        isInNet(dnsResolve(host), "192.168.0.0", "255.255.0.0") ||
        isInNet(dnsResolve(host), "127.0.0.0", "255.0.0.0")) {
        return "DIRECT";
    }
    
    // ARIMデータポータル関連はプロキシ経由
    if (shExpMatch(host, "*arim*") ||
        shExpMatch(host, "*nims*") ||
        shExpMatch(host, "*mdr*")) {
        return "PROXY 127.0.0.1:8888; DIRECT";
    }
    
    // その他の外部サイトもプロキシ経由
    return "PROXY 127.0.0.1:8888; DIRECT";
}
""".strip()


class PACRequestHandler(http.server.SimpleHTTPRequestHandler):
    """PACファイル配布専用HTTPハンドラー"""
    
    def do_GET(self):
        """GET リクエストの処理"""
        if self.path in ['/proxy.pac', '/wpad.dat', '/']:
            self._serve_pac_file()
        else:
            self.send_error(404, "PAC file not found")
    
    def _serve_pac_file(self):
        """PACファイルの配布"""
        try:
            # PACファイル内容を動的に調整
            pac_content = self._get_pac_content()
            
            # HTTPレスポンス
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-ns-proxy-autoconfig')
            self.send_header('Content-Length', str(len(pac_content.encode('utf-8'))))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            
            # ボディ送信
            self.wfile.write(pac_content.encode('utf-8'))
            
            print(f"[PAC] Served PAC file to {self.client_address[0]}")
            
        except Exception as e:
            print(f"[PAC] Error serving PAC file: {e}")
            self.send_error(500, str(e))
    
    def _get_pac_content(self) -> str:
        """PACファイル内容の生成"""
        # サーバー設定に基づいてPAC内容を調整
        pac_content = DEFAULT_PAC_CONTENT
        
        # プロキシポート番号を動的に設定
        if hasattr(self.server, 'proxy_port'):
            pac_content = pac_content.replace('127.0.0.1:8888', f'127.0.0.1:{self.server.proxy_port}')
        
        return pac_content
    
    def log_message(self, format, *args):
        """ログメッセージ（必要最小限のみ）"""
        if "GET /proxy.pac" in format % args or "GET /wpad.dat" in format % args:
            print(f"[PAC] {format % args}")


class PACServer:
    """PACファイル配布サーバー管理"""
    
    def __init__(self, port: int = 8080, proxy_port: int = 8888):
        self.port = port
        self.proxy_port = proxy_port
        self.server: Optional[socketserver.TCPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False
    
    def start(self) -> bool:
        """PACサーバー開始"""
        try:
            self.server = socketserver.TCPServer(("127.0.0.1", self.port), PACRequestHandler)
            self.server.allow_reuse_address = True
            self.server.proxy_port = self.proxy_port  # プロキシポート情報を渡す
            
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            
            self.running = True
            print(f"✅ PACサーバー開始: http://127.0.0.1:{self.port}/proxy.pac")
            
            # 起動確認
            time.sleep(0.5)
            return True
            
        except Exception as e:
            print(f"❌ PACサーバー開始失敗: {e}")
            return False
    
    def stop(self) -> None:
        """PACサーバー停止"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.running = False
            print(f"✅ PACサーバー停止: port {self.port}")
    
    def is_running(self) -> bool:
        """動作状況確認"""
        return self.running and self.thread is not None and self.thread.is_alive()
    
    def get_pac_url(self) -> str:
        """PAC URL を取得"""
        return f"http://127.0.0.1:{self.port}/proxy.pac"


def main():
    """メイン実行（サーバー単体起動用）"""
    import argparse
    
    parser = argparse.ArgumentParser(description="PACファイル配布サーバー")
    parser.add_argument("--port", type=int, default=8080, help="PACサーバーポート番号")
    parser.add_argument("--proxy-port", type=int, default=8888, help="プロキシサーバーポート番号")
    parser.add_argument("--duration", type=int, default=0, help="実行時間（秒、0=無制限）")
    
    args = parser.parse_args()
    
    pac_server = PACServer(port=args.port, proxy_port=args.proxy_port)
    
    if pac_server.start():
        try:
            print(f"📁 PAC URL: {pac_server.get_pac_url()}")
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
            pac_server.stop()
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
