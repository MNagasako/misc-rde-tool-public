#!/usr/bin/env python3

"""
RDEシステムのHTTPリクエスト/レスポンスを分析・調査するツール。
APIエンドポイントの動作解析やデータセット開設フローの調査支援用。
プロキシ対応: net.httpラッパーを使用してプロキシ設定を透過的に適用
※本番環境での利用は非推奨。
"""



import sys
import os
import json
import logging
import argparse
# === セッション管理ベースのプロキシ対応 ===
from classes.utils.api_request_helper import api_request
from net.session_manager import get_proxy_session
# 型定義用インポート
try:
    import requests as _requests_types
except ImportError:
    from net import _requests_types
from datetime import datetime
from typing import Dict, Any, Optional, List

# パス管理システムを使用（CWD非依存）
from config.common import get_cookie_file_path, OUTPUT_LOG_DIR
# v2.0.3: BEARER_TOKEN_FILE削除、load_bearer_tokenを使用


class RDERequestAnalyzer:
    def get_bearer_token_simple(self, response: _requests_types.Response) -> Optional[str]:
        """
        bearer_tokens.json からトークンを取得（v2.0.3: JSON形式のみ）
        """
        try:
            from config.common import load_bearer_token
            self.logger.info("[DEBUG] get_bearer_token_simple: bearer_tokens.jsonから取得")
            token = load_bearer_token('rde.nims.go.jp')
            if token:
                self.logger.info(f"[SUCCESS] トークン取得成功: {token[:20]}...")
                return token
            else:
                self.logger.warning("[WARN] トークンが見つかりません")
                return None
        except Exception as e:
            self.logger.error(f"[ERROR] トークン読み込み失敗: {e}")
            return None
    
    def __init__(self, log_to_file: bool = True):
        """
        :param log_to_file: ファイルにログ出力する場合True
        """
        self.session = get_proxy_session()
        self.log_to_file = log_to_file
        self.log_data = []
        
        # ログ設定
        self.logger = logging.getLogger("RDERequestAnalyzer")
        self.logger.setLevel(logging.DEBUG)
        
        # コンソールハンドラー
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            logging.Formatter('[%(levelname)s] %(asctime)s - %(message)s')
        )
        self.logger.addHandler(console_handler)
        
        # ファイルハンドラー（オプション）
        if log_to_file:
            log_file = os.path.join(OUTPUT_LOG_DIR, "rde_request_analyzer.log")
            os.makedirs(OUTPUT_LOG_DIR, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(
                logging.Formatter('[%(levelname)s] %(asctime)s - %(message)s')
            )
            self.logger.addHandler(file_handler)
    
    def load_cookies(self, cookie_file_path: Optional[str] = None) -> bool:
        """
        Cookieファイルからセッション情報を読み込む
        :return: 成功時True
        """
        if cookie_file_path is None:
            cookie_file_path = get_cookie_file_path()
        
        try:
            if os.path.exists(cookie_file_path):
                with open(cookie_file_path, 'r', encoding='utf-8') as f:
                    cookies_data = json.load(f)
                
                # Cookieを設定
                for cookie in cookies_data:
                    self.session.cookies.set(cookie['name'], cookie['value'])
                
                self.logger.info(f"Cookie読み込み成功: {len(cookies_data)}件")
                return True
            else:
                self.logger.warning(f"Cookieファイルが見つかりません: {cookie_file_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Cookie読み込みエラー: {e}")
            return False
    
    def make_request(self, method: str, url: str, headers: Optional[Dict[str, str]] = None, 
                    data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, str]] = None,
                    json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        HTTPリクエスト送信・詳細ログ記録
        """
        timestamp = datetime.now().isoformat()
        
        # デフォルトヘッダー設定
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        if headers:
            default_headers.update(headers)
        
        # リクエスト情報をログ出力
        self.logger.info(f"=== HTTPリクエスト開始 ===")
        self.logger.info(f"時刻: {timestamp}")
        self.logger.info(f"メソッド: {method}")
        self.logger.info(f"URL: {url}")
        self.logger.info(f"ヘッダー: {json.dumps(default_headers, indent=2, ensure_ascii=False)}")
        
        if params:
            self.logger.info(f"URLパラメータ: {json.dumps(params, indent=2, ensure_ascii=False)}")
        
        if data:
            self.logger.info(f"フォームデータ: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        if json_data:
            self.logger.info(f"JSONデータ: {json.dumps(json_data, indent=2, ensure_ascii=False)}")
        
        try:
            # リクエスト送信
            response = self.session.request(
                method=method,
                url=url,
                headers=default_headers,
                data=data,
                params=params,
                json=json_data,
                timeout=180
            )
            
            # レスポンス情報をログ出力
            self.logger.info(f"=== HTTPレスポンス受信 ===")
            self.logger.info(f"ステータスコード: {response.status_code}")
            self.logger.info(f"レスポンスヘッダー: {json.dumps(dict(response.headers), indent=2, ensure_ascii=False)}")
            
            # レスポンスボディの処理
            try:
                if response.headers.get('content-type', '').startswith('application/json'):
                    response_body = response.json()
                    self.logger.info(f"レスポンスボディ（JSON）: {json.dumps(response_body, indent=2, ensure_ascii=False)}")
                else:
                    response_body = response.text
                    if len(response_body) > 1000:
                        self.logger.info(f"レスポンスボディ（HTML/テキスト）: {response_body[:1000]}... (truncated)")
                    else:
                        self.logger.info(f"レスポンスボディ（HTML/テキスト）: {response_body}")
                        
            except Exception as e:
                response_body = f"レスポンスボディ読み取りエラー: {e}"
                self.logger.error(response_body)
            
            # 構造化データとして記録
            request_data = {
                'timestamp': timestamp,
                'request': {
                    'method': method,
                    'url': url,
                    'headers': default_headers,
                    'params': params,
                    'data': data,
                    'json': json_data
                },
                'response': {
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'body': response_body,
                    'url': response.url,
                    'history': [r.url for r in response.history]  # リダイレクト履歴
                }
            }
            
            self.log_data.append(request_data)
            
            # リダイレクト情報
            if response.history:
                self.logger.info(f"リダイレクト履歴: {[r.url for r in response.history]}")
            
            self.logger.info(f"=== リクエスト・レスポンス記録完了 ===\n")
            
            return request_data
            
        except Exception as e:
            error_data = {
                'timestamp': timestamp,
                'request': {
                    'method': method,
                    'url': url,
                    'headers': default_headers,
                    'params': params,
                    'data': data,
                    'json': json_data
                },
                'error': str(e)
            }
            
            self.log_data.append(error_data)
            self.logger.error(f"リクエストエラー: {e}")
            
            return error_data
    
    def save_log_to_file(self, filename: Optional[str] = None) -> str:
        """
        ログデータをJSONファイル保存
        :return: 保存ファイルパス
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"rde_request_analysis_{timestamp}.json"
        
        file_path = os.path.join(OUTPUT_LOG_DIR, filename)
        os.makedirs(OUTPUT_LOG_DIR, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.log_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"ログデータ保存完了: {file_path}")
        return file_path
    
    def get_csrf_token(self, url: str) -> Optional[str]:
        """
        指定URLからCSRFトークンを取得
        """
        try:
            response = self.session.get(url)
            csrf_token = self.get_csrf_token_from_response(response)
            
            if csrf_token:
                return csrf_token
            
            # 基本的な方法で見つからない場合、代替方法を試す
            self.logger.info("[CSRF_RETRY] Trying alternative methods...")
            base_url = '/'.join(url.split('/')[:3])  # プロトコル + ドメイン
            return self.try_csrf_alternative_methods(base_url)
            
        except Exception as e:
            self.logger.error(f"CSRFトークン取得エラー: {e}")
            return None
        
    def get_csrf_token_from_response(self, response: _requests_types.Response) -> Optional[str]:
        """
        レスポンスからCSRFトークンを抽出
        """
        try:
            # --- 新しい認証トークン取得メソッドの呼び出し例 ---
            dummy_bearer = self.get_bearer_token_simple(response)
            self.logger.info(f"[DEBUG] get_bearer_token_simpleの結果: {dummy_bearer}")
            if dummy_bearer:
                self.logger.info(f"[SUCCESS] get_bearer_token_simpleで認証トークン取得: {dummy_bearer[:20]}...")
                return dummy_bearer
            else:
                return None
            
        except Exception as e:
            self.logger.error(f"CSRFトークン抽出エラー: {e}")
            return None
    
    def try_csrf_alternative_methods(self, base_url: str) -> Optional[str]:
        """
        代替手段でCSRFトークン取得
        """
        try:
            # 方法1: ログインページからCSRFトークンを取得
            login_endpoints = [
                f"{base_url}/login",
                f"{base_url}/auth/login", 
                f"{base_url}/api/auth/csrf",
                f"{base_url}/sanctum/csrf-cookie"
            ]
            
            for endpoint in login_endpoints:
                try:
                    self.logger.info(f"[CSRF_ALT] Trying endpoint: {endpoint}")
                    response = self.session.get(endpoint, timeout=10)
                    
                    if response.status_code == 200:
                        csrf_token = self.get_csrf_token_from_response(response)
                        if csrf_token:
                            self.logger.info(f"[CSRF_SUCCESS] Token found via {endpoint}")
                            return csrf_token
                            
                except Exception as e:
                    self.logger.debug(f"[CSRF_ALT] Failed {endpoint}: {e}")
                    continue
            
            # 方法2: APIエンドポイントからヘッダー情報を取得
            api_endpoints = [
                f"{base_url}/api/user/profile",
                f"{base_url}/api/datasets",
                f"{base_url}/api/auth/me"
            ]
            
            for endpoint in api_endpoints:
                try:
                    self.logger.info(f"[CSRF_API] Trying API endpoint: {endpoint}")
                    response = self.session.get(endpoint, timeout=10)
                    
                    # ヘッダーからCSRFトークンを確認
                    csrf_headers = ['X-CSRF-TOKEN', 'x-csrf-token', 'csrf-token']
                    for header in csrf_headers:
                        if header in response.headers:
                            token = response.headers[header]
                            self.logger.info(f"[CSRF_HEADER] Found via {endpoint} header {header}")
                            return token
                            
                except Exception as e:
                    self.logger.debug(f"[CSRF_API] Failed {endpoint}: {e}")
                    continue
            
            self.logger.warning("[CSRF_ALT] All alternative methods failed")
            return None
            
        except Exception as e:
            self.logger.error(f"代替CSRF取得エラー: {e}")
            return None
    
    def prepare_request_without_csrf(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        CSRFトークンなしでリクエスト準備
        """
        try:
            self.logger.info("[NO_CSRF] Preparing request without CSRF token")
            
            # ヘッダーの準備
            headers = kwargs.get('headers', {})
            
            # セッションベース認証のヘッダーを追加
            headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                #'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                #'X-Requested-With': 'XMLHttpRequest',
            })
            
            # Refererヘッダーを設定（CSRF保護の緩和）
            if 'Referer' not in headers:
                base_url = '/'.join(url.split('/')[:3])
                headers['Referer'] = base_url
            
            # Originヘッダーを設定
            if 'Origin' not in headers:
                base_url = '/'.join(url.split('/')[:3])
                headers['Origin'] = base_url
            
            kwargs['headers'] = headers
            
            self.logger.info(f"[NO_CSRF] Request prepared with session-based auth")
            return kwargs
            
        except Exception as e:
            self.logger.error(f"CSRFなしリクエスト準備エラー: {e}")
            return kwargs

def main():
    """コマンドライン実行用エントリポイント"""
    parser = argparse.ArgumentParser(description='RDE HTTPリクエスト・レスポンス調査ツール')
    parser.add_argument('--method', '-m', default='GET', help='HTTPメソッド (GET, POST, PUT, DELETE等)')
    parser.add_argument('--url', '-u', required=True, help='リクエストURL')
    parser.add_argument('--headers', '-H', help='リクエストヘッダー (JSON形式)')
    parser.add_argument('--data', '-d', help='フォームデータ (JSON形式)')
    parser.add_argument('--params', '-p', help='URLパラメータ (JSON形式)')
    parser.add_argument('--json', '-j', help='JSONデータ (JSON形式)')
    parser.add_argument('--cookie-file', '-c', help='Cookieファイルパス')
    parser.add_argument('--no-log-file', action='store_true', help='ファイルログを無効化')
    parser.add_argument('--output', '-o', help='ログ出力ファイル名')
    
    args = parser.parse_args()
    
    # 解析ツール初期化
    analyzer = RDERequestAnalyzer(log_to_file=not args.no_log_file)
    
    # Cookie読み込み
    if args.cookie_file:
        analyzer.load_cookies(args.cookie_file)
    else:
        analyzer.load_cookies()  # デフォルトパス
    
    # パラメータ解析
    headers = json.loads(args.headers) if args.headers else None
    data = json.loads(args.data) if args.data else None
    params = json.loads(args.params) if args.params else None
    json_data = json.loads(args.json) if args.json else None
    
    # リクエスト実行
    result = analyzer.make_request(
        method=args.method,
        url=args.url,
        headers=headers,
        data=data,
        params=params,
        json_data=json_data
    )
    
    # ログ保存
    if not args.no_log_file:
        analyzer.save_log_to_file(args.output)
    
    print(f"\n=== 実行結果 ===")
    print(f"リクエスト: {args.method} {args.url}")
    if 'response' in result:
        print(f"ステータスコード: {result['response']['status_code']}")
        print(f"レスポンスURL: {result['response']['url']}")
    else:
        print(f"エラー: {result.get('error', 'Unknown error')}")


if __name__ == "__main__":
    main()
