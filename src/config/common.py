
#!/usr/bin/env python3
"""
共通設定ファイル - ARIM RDE Tool

概要:
アプリケーション全体で使用される共通設定、パス管理、
定数定義を一元管理するモジュールです。

主要機能:
- バージョン・リビジョン管理
- 開発時/バイナリ時の動的パス管理
- ディレクトリ構造の自動生成
- 設定ファイルパスの一元管理
- 環境依存設定の抽象化

設計思想:
PyInstallerでのバイナリ化時とソースコード実行時の
パス解決を透過的に処理し、環境に依存しない
堅牢なファイルアクセスを実現します。
"""

import sys
import os

# バージョン管理
# リリース時は以下の場所も更新必要:
# 1. ドキュメント: VERSION.txt, README.md, docs/refactor_progress.md
# 2. 各クラスファイル: ヘッダーコメント内のバージョン番号
# 3. このREVISION変数（マスター管理）
# 2025-10-31: v1.19.2 - ARIM報告書スクレイピング修正・AI拡張タブ検索補完機能強化
REVISION = "1.19.2"  # リビジョン番号（バージョン管理用）- 【注意】変更時は上記場所も要更新
# 2025-10-31: v1.19.1 - QWidgetサイズエラー修正・AI Test 2ボタン安定化
# 2025-10-22: v1.18.5 - 安定性向上・軽微な修正・バージョン統一
# 2025-10-21: v1.18.4 - 軽微なバグ修正・安定性向上・バージョン統一
# 2025-09-10: v1.17.2 - センシティブデータ保護強化・コードクリーンアップ・ライセンス管理強化
# 2025-08-31: v1.15.0 - ワークスペース大規模整理完了・コードベース品質向上・開発環境安定化
# 2025-08-28: v1.14.1 - 企業CA証明書機能有効化・SSL証明書管理完全対応・PyInstaller配布対応
# 2025-08-28: v1.14.0 - プロキシ対応機能完全実装・エラーメッセージUI改善・ワークスペース整理
# 2025-08-27: v1.13.5 - サブグループメンバー選択UI大幅改善・テーブル形式・ソート機能対応
# 2025-08-27: v1.13.4 - データセット選択フィルタ機能大幅強化・複合フィルタ対応・ユーザビリティ向上
# 2025-08-26: v1.13.3 - AI分析UI改善・プログレス表示復旧・ユーザビリティ向上
# 2025-08-24: v1.13.2 - リファクタリング継続・フォーム機能分離・コードベース整備継続
# 2025-08-22: v1.13.1 - バグ修正・機能改善
# 2025-08-19: v1.12.6 - データセット登録・開設UIバグ修正（PyQt5 import scope error解決）
# 2025-08-18: v1.12.5 - AI機能レスポンス情報表示強化・統合テストツール追加
# 2025-08-17: v1.12.4 - パス依存修正・バイナリ化対応強化（PyInstaller互換性向上）

# 外部化推奨定数（設定値）
# 画像表示を待つ時間（ミリ秒）
IMAGE_LOAD_WAIT_TIME = 5000  
# RDEサービスのベースURL
RDE_BASE_URL = "https://rde.nims.go.jp"
RDE_API_BASE_URL = "https://rde-api.nims.go.jp"
# User-Agent（APIアクセス用）
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# パス管理システム（ソース時=メインコード基準 / バイナリ時=EXE基準・CWD非依存）

def is_binary_execution():
    """
    バイナリ実行かソース実行かを判定
    Returns:
        bool: バイナリ実行時True, ソース実行時False
    """
    return hasattr(sys, '_MEIPASS')

def get_base_dir():
    """
    実行環境に応じた基準ディレクトリを取得（CWD非依存）
    - ソース実行時: メインソースファイル（arim_rde_tool.py）を基準
    - バイナリ実行時: 実行ファイル（arim_rde_tool.exe）を基準
    
    Returns:
        str: 基準ディレクトリの絶対パス
    """
    if is_binary_execution():
        # バイナリ実行時: 実行ファイル（arim_rde_tool.exe）のディレクトリ
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        # ソース実行時: メインソースファイル（arim_rde_tool.py）のディレクトリの親
        # src/config/common.py -> src -> project_root（arim_rde_tool.pyの親）
        current_file_dir = os.path.dirname(os.path.abspath(__file__))  # src/config
        src_dir = os.path.dirname(current_file_dir)  # src
        project_root = os.path.dirname(src_dir)  # project_root
        return project_root

def get_static_resource_path(relative_path):
    """
    静的リソースファイルのパスを取得
    - ソース実行時: src/相対パスで参照
    - バイナリ実行時: _MEIPASS/相対パスで参照
    
    Args:
        relative_path (str): 静的リソースへの相対パス（例: "image/icon.ico"）
    
    Returns:
        str: 静的リソースファイルの絶対パス
    """
    # パスセパレータを正規化
    path_parts = relative_path.replace('/', os.sep).replace('\\', os.sep).split(os.sep)
    
    if is_binary_execution():
        # バイナリ実行時: _MEIPASS配下から取得
        return os.path.join(sys._MEIPASS, *path_parts)
    else:
        # ソース実行時: src/相対パスで取得
        current_file_dir = os.path.dirname(os.path.abspath(__file__))  # src/config
        src_dir = os.path.dirname(current_file_dir)  # src
        return os.path.join(src_dir, *path_parts)

def get_dynamic_file_path(relative_path):
    """
    動的フォルダ（input/output）のパスを取得
    - ソース実行時: project_root/相対パスで参照
    - バイナリ実行時: exe_dir/相対パスで参照
    
    Args:
        relative_path (str): 動的フォルダへの相対パス（例: "input/data.xlsx"）
    
    Returns:
        str: 動的ファイルの絶対パス
    """
    # パスセパレータを正規化
    path_parts = relative_path.replace('/', os.sep).replace('\\', os.sep).split(os.sep)
    return os.path.join(get_base_dir(), *path_parts)

# ディレクトリ自動作成とパス定義

# 基準ディレクトリの取得
BASE_DIR = get_base_dir()

# 入力・出力・設定ディレクトリの定義と自動作成
INPUT_DIR = get_dynamic_file_path('input')
OUTPUT_DIR = get_dynamic_file_path('output')
OUTPUT_LOG_DIR = get_dynamic_file_path('output/log')
HIDDEN_DIR = get_dynamic_file_path('output/.private')
CONFIG_DIR = get_dynamic_file_path('config')

OUTPUT_RDE_DIR = get_dynamic_file_path('output/rde')
# dataFilesディレクトリの定数
DATAFILES_DIR = get_dynamic_file_path('output/rde/data/dataFiles')
# samplesディレクトリの定数
SAMPLES_DIR = get_dynamic_file_path('output/rde/data/samples')

# ディレクトリの自動作成
for dir_path in [INPUT_DIR, OUTPUT_DIR, OUTPUT_LOG_DIR, HIDDEN_DIR, CONFIG_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)

# 便利関数: output ディレクトリパスを取得
def get_output_directory():
    """outputディレクトリの絶対パスを返す"""
    return OUTPUT_DIR

def get_input_directory():
    """inputディレクトリの絶対パスを返す"""
    return INPUT_DIR

# ファイルパス定義（動的ファイル）

# セキュリティ関連ファイル
COOKIE_FILE_RDE = os.path.join(HIDDEN_DIR, '.cookies_rde.txt')
DEBUG_INFO_FILE = os.path.join(HIDDEN_DIR, 'info.txt')
BEARER_TOKEN_FILE = os.path.join(HIDDEN_DIR, 'bearer_token.txt')  # レガシー互換用（rde.nims.go.jp）
BEARER_TOKENS_FILE = os.path.join(HIDDEN_DIR, 'bearer_tokens.json')  # 複数ホスト対応（v1.18.3+）

# 入力ファイル
ARIM_BATCH_LIST_FILE = get_dynamic_file_path('input/list.txt')
LOGIN_FILE = get_dynamic_file_path('input/login.txt')

# 出力ファイル
SUMMARY_XLSX_PATH = get_dynamic_file_path('output/summary.xlsx')

# ログファイル
DEBUG_LOG_PATH = get_dynamic_file_path('output/log/debug_trace.log')
WEBVIEW_HTML_DIR = get_dynamic_file_path('output/log/webview_html')
WEBVIEW_LOG_FILE = get_dynamic_file_path('output/log/webview_log.html')
WEBVIEW_URL_LOG_FILE = get_dynamic_file_path('output/log/webview_url_log.txt')
WEBVIEW_HTML_MAP_FILE = get_dynamic_file_path('output/log/webview_html_map.txt')
SEARCH_RESULT = get_dynamic_file_path('output/log/search_result.html')
WEBVIEW_MESSAGE_LOG = get_dynamic_file_path('output/log/webview_message.log')

# データセット関連
DATASETS_DIR = get_dynamic_file_path('output/datasets')
DATASET_DETAILS_DIR = get_dynamic_file_path('output/datasets')
DATATREE_FILE_NAME = '.datatree.json'
NEW_DATATREE_FILE_NAME = '.datatree.new.json'
DATATREE_FILE_PATH = os.path.join(DATASET_DETAILS_DIR, NEW_DATATREE_FILE_NAME)

# RDEデータファイル
OUTPUT_RDE_DATA_DIR = get_dynamic_file_path('output/rde/data')
DATASET_JSON_PATH = get_dynamic_file_path('output/rde/data/dataset.json')
INFO_JSON_PATH = get_dynamic_file_path('output/rde/data/info.json')
SELF_JSON_PATH = get_dynamic_file_path('output/rde/data/self.json')
SUBGROUP_JSON_PATH = get_dynamic_file_path('output/rde/data/subGroup.json')
TEMPLATE_JSON_PATH = get_dynamic_file_path('output/rde/data/template.json')
INSTRUMENTS_JSON_PATH = get_dynamic_file_path('output/rde/data/instruments.json')
LICENSES_JSON_PATH = get_dynamic_file_path('output/rde/data/licenses.json')
INSTRUMENT_TYPE_JSON_PATH = get_dynamic_file_path('output/rde/data/instrumentType.json')
ORGANIZATION_JSON_PATH = get_dynamic_file_path('output/rde/data/organization.json')
GROUP_DETAIL_JSON_PATH = get_dynamic_file_path('output/rde/data/groupDetail.json')
DATA_ENTRY_DIR = get_dynamic_file_path('output/rde/data/dataEntry')

# 画像ディレクトリ（動的生成）
DYNAMIC_IMAGE_DIR = get_dynamic_file_path('output/images')
PROXY_IMAGE_DIR = get_dynamic_file_path('output/proxy_images')

# 検索結果ディレクトリ
SEARCH_RESULTS_DIR = get_dynamic_file_path('output/search_results')

# 動的ディレクトリの自動作成
for dir_path in [WEBVIEW_HTML_DIR, DATASETS_DIR, DYNAMIC_IMAGE_DIR, PROXY_IMAGE_DIR, SEARCH_RESULTS_DIR, OUTPUT_RDE_DATA_DIR, DATA_ENTRY_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
        
# アプリケーション設定パラメータ

# デフォルトgrantNumber
DEFAULT_GRANT_NUMBER = 'JPMXP1222TU0195'

# 画像保存・ポーリング等のパラメータ
TEST_BLOB_LIMIT = 100  # blob画像保存の最大数
MAX_POLL = 100       # ポーリング最大回数
POLL_INTERVAL = 200  # ポーリング間隔(ms)
MAX_WEBVIEW_MSG_LEN = 110  # WebViewメッセージ最大長
MAX_IMAGES_PER_DATASET = 3  # デフォルトは3件（画像取得上限）

# 静的リソースファイルパス

# 静的データのパス（開発時とバイナリ時で異なる場所から取得）
JS_TEMPLATES_DIR = get_static_resource_path('js_templates')
STATIC_IMAGE_DIR = get_static_resource_path('image')

# 関数定義

def get_cookie_file_path():
    """Cookieファイルのパスを取得"""
    return COOKIE_FILE_RDE

def get_samples_dir_path():
    """samplesディレクトリのパスを取得"""
    return SAMPLES_DIR

def get_user_config_dir():
    """ユーザー設定ディレクトリのパスを取得"""
    return get_dynamic_file_path("config")

# =============================================================================
# 複数ホスト対応 Bearer Token 管理機能（v1.18.3+）
# =============================================================================

import json as _json
from typing import Optional, Dict

# RDEホスト定義
RDE_HOSTS = {
    'rde': 'rde.nims.go.jp',
    'rde-material': 'rde-material.nims.go.jp'
}

def save_bearer_token(token: str, host: str = 'rde.nims.go.jp') -> bool:
    """
    Bearer Tokenを保存（複数ホスト対応）
    
    Args:
        token: 保存するBearerトークン
        host: ホスト名（例: 'rde.nims.go.jp', 'rde-material.nims.go.jp'）
    
    Returns:
        bool: 保存成功時True
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        
        # 既存のトークンを読み込み
        logger.debug(f"[TOKEN-SAVE] 既存トークンを読み込み: {BEARER_TOKENS_FILE}")
        print(f"[TOKEN-SAVE] 保存開始 - host={host}, token={token[:20]}...")
        tokens = load_all_bearer_tokens()
        print(f"[TOKEN-SAVE] 既存トークン数: {len(tokens)}, ホスト: {list(tokens.keys())}")
        
        # 新しいトークンを追加
        tokens[host] = token
        logger.info(f"[TOKEN-SAVE] トークンを追加: host={host}, token={token[:20]}...")
        print(f"[TOKEN-SAVE] 追加後トークン数: {len(tokens)}, ホスト: {list(tokens.keys())}")
        
        # JSON形式で保存
        logger.debug(f"[TOKEN-SAVE] JSON形式で保存: {BEARER_TOKENS_FILE}")
        with open(BEARER_TOKENS_FILE, 'w', encoding='utf-8') as f:
            _json.dump(tokens, f, indent=2, ensure_ascii=False)
        logger.info(f"[TOKEN-SAVE] JSON保存完了: {len(tokens)}個のトークン")
        print(f"[TOKEN-SAVE] JSON保存完了: {BEARER_TOKENS_FILE}")
        
        # 保存後の確認
        saved_tokens = load_all_bearer_tokens()
        print(f"[TOKEN-SAVE] 保存確認 - ホスト数: {len(saved_tokens)}, ホスト: {list(saved_tokens.keys())}")
        for saved_host, saved_token in saved_tokens.items():
            print(f"[TOKEN-SAVE]   {saved_host}: {saved_token[:20]}...")
        
        # レガシー互換：rde.nims.go.jpの場合は従来のファイルにも保存
        if host == 'rde.nims.go.jp':
            logger.debug(f"[TOKEN-SAVE] レガシーファイルにも保存: {BEARER_TOKEN_FILE}")
            with open(BEARER_TOKEN_FILE, 'w', encoding='utf-8') as f:
                f.write(f"BearerToken={token}\n")
            logger.info("[TOKEN-SAVE] レガシーファイル保存完了")
        
        return True
    except Exception as e:
        print(f"[TOKEN-SAVE] Bearer Token保存エラー ({host}): {e}")
        logger.error(f"Bearer Token保存エラー ({host}): {e}")
        return False

def load_bearer_token(host: str = 'rde.nims.go.jp') -> Optional[str]:
    """
    指定ホストのBearer Tokenを取得
    
    Args:
        host: ホスト名（例: 'rde.nims.go.jp', 'rde-material.nims.go.jp'）
    
    Returns:
        str: トークン文字列、存在しない場合None
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        
        print(f"[TOKEN-LOAD] トークン読み込み開始 - host={host}")
        logger.debug(f"[TOKEN-LOAD] トークン読み込み開始: host={host}")
        
        # 新形式のJSONファイルから読み込み
        if os.path.exists(BEARER_TOKENS_FILE):
            logger.debug(f"[TOKEN-LOAD] JSON形式トークンファイル読み込み: {BEARER_TOKENS_FILE}")
            print(f"[TOKEN-LOAD] JSONファイルから読み込み中...")
            with open(BEARER_TOKENS_FILE, 'r', encoding='utf-8') as f:
                tokens = _json.load(f)
                print(f"[TOKEN-LOAD] ファイル内のホスト数: {len(tokens)}, ホスト: {list(tokens.keys())}")
                if host in tokens:
                    token = tokens[host]
                    logger.info(f"[TOKEN-LOAD] トークン読み込み成功 ({host}): {token[:20]}...")
                    print(f"[TOKEN-LOAD] トークン取得成功 - host={host}, token={token[:20]}...")
                    return token
                else:
                    logger.warning(f"[TOKEN-LOAD] ホスト {host} のトークンが見つかりません")
                    print(f"[TOKEN-LOAD] 指定ホストのトークンなし - host={host}")
        else:
            logger.debug(f"[TOKEN-LOAD] JSON形式トークンファイルが存在しません: {BEARER_TOKENS_FILE}")
            print(f"[TOKEN-LOAD] JSONファイルが存在しません")
        
        # レガシー互換：rde.nims.go.jpの場合は従来のファイルからも読み込み
        if host == 'rde.nims.go.jp' and os.path.exists(BEARER_TOKEN_FILE):
            logger.debug(f"[TOKEN-LOAD] レガシートークンファイル読み込み: {BEARER_TOKEN_FILE}")
            print(f"[TOKEN-LOAD] レガシーファイルから読み込み試行")
            with open(BEARER_TOKEN_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # "BearerToken=" プレフィックスを除去
                if content.startswith('BearerToken='):
                    content = content[len('BearerToken='):]
                if content:
                    logger.info(f"[TOKEN-LOAD] レガシーファイルからトークン読み込み成功: {content[:20]}...")
                    print(f"[TOKEN-LOAD] レガシーファイルから取得成功 - token={content[:20]}...")
                    return content
        
        logger.warning(f"[TOKEN-LOAD] トークンが見つかりません ({host})")
        print(f"[TOKEN-LOAD] トークンが見つかりませんでした - host={host}")
        return None
    except Exception as e:
        print(f"[TOKEN-LOAD] Bearer Token読み込みエラー ({host}): {e}")
        logger.error(f"Bearer Token読み込みエラー ({host}): {e}")
        return None

def load_all_bearer_tokens() -> Dict[str, str]:
    """
    全ホストのBearer Tokenを取得
    
    Returns:
        dict: {host: token} の辞書
    """
    try:
        if os.path.exists(BEARER_TOKENS_FILE):
            with open(BEARER_TOKENS_FILE, 'r', encoding='utf-8') as f:
                return _json.load(f)
        return {}
    except Exception as e:
        print(f"Bearer Token一括読み込みエラー: {e}")
        return {}

def get_bearer_token_for_url(url: str) -> Optional[str]:
    """
    URL文字列から適切なBearer Tokenを自動選択
    v1.18.4: rde-instrument-api, rde-entry-api-arim対応強化
    
    Args:
        url: APIエンドポイントのURL
    
    Returns:
        str: 適切なトークン、見つからない場合None
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 優先順位: より具体的なホスト名を優先してマッチング
    
    # 1. rde-material.nims.go.jp関連の派生ホスト（Material専用トークン）
    material_hosts = [
        'rde-material-api.nims.go.jp',
        'rde-material.nims.go.jp'
    ]
    
    for host in material_hosts:
        if host in url:
            token = load_bearer_token('rde-material.nims.go.jp')
            if token:
                logger.debug(f"[TOKEN-SELECT] Material token selected for: {url[:50]}...")
                print(f"[TOKEN-SELECT] Material token for {host}")
                return token
            else:
                logger.warning(f"[TOKEN-SELECT] Material token not found, falling back to RDE token")
                print(f"[TOKEN-SELECT] Material token not found, using RDE token")
    
    # 2. rde.nims.go.jp関連の派生ホスト（RDEメイントークン）
    # 注意: rde-entry-api-arim, rde-instrument-apiもRDEメイントークンを使用
    rde_hosts = [
        'rde-entry-api-arim.nims.go.jp',  # ARIM登録API
        'rde-instrument-api.nims.go.jp',  # 装置情報API
        'rde-api.nims.go.jp',             # メインAPI
        'rde-user-api.nims.go.jp',        # ユーザーAPI
        'rde.nims.go.jp'                  # ベースURL
    ]
    
    for host in rde_hosts:
        if host in url:
            token = load_bearer_token('rde.nims.go.jp')
            if token:
                logger.debug(f"[TOKEN-SELECT] RDE token selected for: {url[:50]}...")
                print(f"[TOKEN-SELECT] RDE token for {host}")
                return token
    
    # 3. デフォルトはrde.nims.go.jpのトークン
    logger.warning(f"[TOKEN-SELECT] No specific host matched, using default RDE token for: {url[:50]}...")
    print(f"[TOKEN-SELECT] Default RDE token for: {url[:50]}...")
    return load_bearer_token('rde.nims.go.jp')

# =============================================================================

DEBUG_LOG_ENABLED = True  # 全体設定で有効/無効切替
# DEBUG設定

# 設定ファイル自動作成機能
def create_default_config_files():
    """起動時にconfigフォルダと設定ファイルを自動作成"""
    
    # network.json のデフォルト内容
    network_json_content = {
        "network": {
            "mode": "DIRECT",
            "proxies": {
                "http": "",
                "https": "",
                "no_proxy": ""
            },
            "pac_url": "",
            "cert": {
                "use_os_store": True,
                "verify": True,
                "ca_bundle": ""
            },
            "timeouts": {
                "connect": 10,
                "read": 30
            },
            "retries": {
                "total": 3,
                "backoff_factor": 0.5,
                "status_forcelist": [429, 500, 502, 503, 504]
            }
        },
        "webview": {
            "auto_proxy_from_network": True,
            "additional_args": []
        }
    }
    
    # network.yaml のデフォルト内容
    network_yaml_content = """network:
  mode: SYSTEM
  proxies:
    http: http://127.0.0.1:8888
    https: http://127.0.0.1:8888
    no_proxy: localhost,127.0.0.1,.local
  pac_url: ''
  cert:
    use_os_store: true
    verify: false
    ca_bundle: ''
    ssl_context_options:
      check_hostname: true
      allow_legacy_unsafe_renegotiation: false
      trust_proxy_certs: false
    proxy_ssl_handling:
      strategy: disable_verify
      fallback_to_no_verify: true
      log_ssl_errors: true
    enterprise_ca:
      enable_truststore: true
      custom_ca_bundle: ''
      auto_detect_corporate_ca: true
      corporate_ca_sources:
      - truststore
      - system_ca
      - certifi
      - custom_file
  pac:
    auto_detect: true
    url: ''
    timeout: 10
    fallback_to_system: true
  timeouts:
    connect: 10
    read: 30
  retries:
    total: 3
    backoff_factor: 0.5
    status_forcelist:
    - 429
    - 500
    - 502
    - 503
    - 504
webview:
  auto_proxy_from_network: true
  additional_args: []
ui:
  show_startup_proxy_notification: false
"""
    
    # network.json の作成
    network_json_path = os.path.join(CONFIG_DIR, 'network.json')
    if not os.path.exists(network_json_path):
        try:
            import json
            with open(network_json_path, 'w', encoding='utf-8') as f:
                json.dump(network_json_content, f, indent=2, ensure_ascii=False)
            print(f"デフォルトconfig作成: {network_json_path}")
        except Exception as e:
            print(f"network.json作成失敗: {e}")
    
    # network.yaml の作成
    network_yaml_path = os.path.join(CONFIG_DIR, 'network.yaml')
    if not os.path.exists(network_yaml_path):
        try:
            with open(network_yaml_path, 'w', encoding='utf-8') as f:
                f.write(network_yaml_content)
            print(f"デフォルトconfig作成: {network_yaml_path}")
        except Exception as e:
            print(f"network.yaml作成失敗: {e}")

# 起動時に設定ファイルを自動作成
create_default_config_files()
DEBUG_LOG_FULL_ARGS = False  # Trueで引数全文、Falseで100文字に切り詰め