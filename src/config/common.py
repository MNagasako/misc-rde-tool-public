
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
import logging
logger = logging.getLogger(__name__)


def _get_this_module_file_path() -> str | None:
    spec = globals().get("__spec__")
    origin = getattr(spec, "origin", None) if spec else None
    if origin and origin != "built-in":
        return origin
    try:
        import inspect

        return inspect.getsourcefile(sys.modules[__name__]) or inspect.getfile(sys.modules[__name__])
    except Exception:
        return None


def _get_src_dir_for_source_execution() -> str:
    module_file_path = _get_this_module_file_path()
    if not module_file_path:
        raise RuntimeError("Failed to resolve module file path for config.common")
    current_file_dir = os.path.dirname(os.path.abspath(module_file_path))  # src/config
    return os.path.dirname(current_file_dir)  # src

# バージョン管理
# リリース時は以下の場所も更新必要:
# 1. ドキュメント: VERSION.txt, README.md, RELEASE_NOTES_v*.md
# 2. 各クラスファイル: ヘッダーコメント内のバージョン番号
# 3. このREVISION変数（マスター管理）
# 2025-11-27: v2.1.9 - データポータルRDE存在確認・ファイルリストUI改善・プロジェクト整理完了
# 2025-11-22: v2.1.8 - AI拡張機能強化（ファイルテキスト抽出設定UI・使用プロンプト表示・設定永続化）
# 2025-12-02: v2.1.14 - データポータル自動設定改善・設備リンク名称付与・テスト追加
# 2025-12-02: v2.1.13 - 公開ページボタン追加・設備リンク化・ユーティリティ/テスト追加
# 2025-12-01: v2.1.12 - データセット修正タブUI改善（関連データ/情報ビルダーダイアログ・日本時間表示）
# 2025-11-29: v2.1.11 - 設定タブ整理・ヘルプドキュメント刷新・ウィンドウ位置ポリシー確定・--log-level導入
# 2025-11-28: v2.1.10 - データセット編集Completerフィルタ選択完全対応・2段階検索実装・テスト強化
# 2025-11-27: v2.1.9 - データポータルRDE存在確認・自動ボタン無効化・ファイルリストUI改善
# 2025-11-22: v2.1.8 - AI拡張ファイルテキスト抽出・プロンプト表示・設定タブ新設
# 2025-11-22: v2.1.7 - テーマ切替最適化完了・不要再処理除去・配色のみ更新・監査完了
# 2025-11-16: v2.1.4 - コードベース全体レビュー・リビジョンアップ・品質改善継続
# 2025-11-15: v2.1.3 - データ取得2機能ファイル単位プログレス表示・粒度改善・スレッドセーフ実装
# 2025-11-15: v2.1.2 - プログレス表示随時更新修正・スレッド安全性向上・repaint実装
# 2025-11-14: v2.0.8 - プロキシ設定完全修正・接続テストUI設定反映・truststore/CA設定統合
# 2025-12-31: v2.3.15 - AI説明文提案: データセットタブ追加 + ログビューア改善 + テスト安定化
# 2026-01-06: v2.4.7 - メール設定の上書きインストール耐性 + 更新後の自動再起動 + テスト安定化（Windows/Qt）
# 2026-01-06: v2.4.6 - テスト実行の安定化（Windows/Qt）+ フルスイート実行の運用改善 + バージョン表記更新
# 2026-01-05: v2.4.5 - テスト/起動連携の決定性改善 + テーマ/パス管理の規約準拠 + バージョン表記更新
# 2026-01-04: v2.4.4 - メール通知タブ: 対象通知リストのフィルタを自動通知にも適用 + 基準日時モード + テンプレ復活防止
# 2026-01-04: v2.4.3 - メール通知タブ: 運用モード/本番宛先の運用改善（表示簡略化・設備管理者宛先追加）
# 2026-01-03: v2.4.2 - データ取得2: メール通知タブ拡張（運用モード/宛先選択/送信ログ閲覧/テンプレ/設備管理者）+ 設備管理者ダイアログ改善
# 2026-01-02: v2.4.1 - データ取得2: メール通知タブ（運用モード/宛先選択/抽出範囲プリセット/送信ログ閲覧/From表示名）
# 2026-01-01: v2.4.0 - データ登録: 登録状況タブ拡張（自動確認/ポーリング/表示高速化/列追加）+ ウィンドウ幅固定不具合修正
# 2025-12-31: v2.3.16 - データエントリー編集（送り状）: 所属/試料モード/レイアウト改善 + スクロール/初期サイズ最適化
# 2025-12-30: v2.3.14 - UI黒化対策（ScrollArea viewport 背景）+ RDE欠落ID除外 + テスト安定化/規約準拠
# 2025-12-29: v2.3.13 - データ構造化XLSX: V6/V7混在のテンプレ列を行ごとに最新版選択 + テスト追加
# 2025-12-29: v2.3.12 - AI説明文提案（結果一覧ログ表示）+ 重要技術領域(nan)表示の空値化 + テスト追加
# 2025-12-29: v2.3.11 - Geminiモデル管理改善（認証方式別）+ APIキー無しモデル取得フォールバック + テスト安定化
# 2025-12-28: v2.3.10 - AI説明文提案（報告書）: 結果一覧に重要技術領域（主/副）列を追加 + テスト決定性改善
# 2025-12-28: v2.3.9 - テスト安定化（Windows/Qt・長時間スイート）+ テーマ追従の破棄後コールバック抑制 + ドキュメント更新
# 2025-12-27: v2.3.8 - テスト安定化（Windows/Qt）+ テーマ切替/モジュール汚染の不具合修正 + ドキュメント更新
# 2025-12-24: v2.3.7 - AI安定化（Gemini MAX_TOKENS復旧）+ 設定画面のSSL警告抑制 + 規約準拠改善
# 2025-12-24: v2.3.6 - データ登録UX改善（通常/一括の完了挙動分離）+ テスト強化
# 2025-12-24: v2.3.5 - テスト安定化・テーマ追従の改善・診断ランナー堅牢化
# 2025-12-23: v2.3.4 - データポータル修正（装置・プロセス関連カタログ生成）+ テスト安定化
# 2025-12-22: v2.3.3 - データセット修正UI改善（関連データ）+ テスト更新/安定化
# 2025-12-21: v2.3.2 - テキストエリア可視性改善（枠線/背景）+ テスト強化
# 2025-12-20: v2.3.1 - データセット機能改善（API再取得・キーボード操作対応）
REVISION = "2.4.7"  # リビジョン番号（バージョン管理用）- 【注意】変更時は上記場所も要更新
# 2025-12-18: v2.2.8 - データセット開設フィルタUI改善 + 基本情報キャッシュ判定修正 + ドキュメント更新
#   - データセット開設（新規開設/新規開設2）: ロール/サブグループ/テンプレート/組織フィルタのラベル整理と「フィルタなし」の追加
#   - 基本情報: サブグループ0件ケースで subGroups/ 欠損扱いにせず、不要な再取得を抑制
#   - リリースノート/ヘルプ/READMEを v2.2.8 に更新し、v2.2.7 リリースノートをアーカイブへ退避
# 2025-12-18: v2.2.7 - Windows/pytest-qt テスト安定化 + バージョン表記更新
#   - pytest実行時のみ、ネイティブUI操作（ダイアログ/可視化/強制processEvents等）を抑制して 0x8001010d 系の致命的クラッシュを回避
#   - invoiceSchema取得時はteamId候補のうち最初の候補のみを使用し、失敗しても他の候補を試行しないように変更
#   - REVISION/VERSION.txt/README/ヘルプ/配布物のバージョン表記を2.2.7へ更新し、旧リリースノートをアーカイブへ退避
# 2025-12-13: v2.2.6 - データポータルアップロードUI改善 + TAGビルダーAI提案追加
#   - データポータルのデータセットアップロード画面で、取得済み画像一覧を4列テーブル化し、キャプション編集/ヘッダ固定/ソート/Up済表示に対応
#   - データセット編集のTAGビルダーに「AI提案」タブを追加し、候補生成→採用/全て採用・リトライ・プロンプト/回答全文確認を実装
#   - REVISION/VERSION.txt/README/ヘルプ/配布物のバージョン表記を2.2.6へ更新し、旧リリースノートをアーカイブへ退避
# 2025-12-10: v2.2.5 - AIサジェスト管理ダイアログ安定化・リリースノート整備
#   - AIExtensionConfigDialog のボタンリスト再描画処理を改善し、レイアウトクリア時にスペーサ/ウィジェット破棄と内部参照を正しく同期
#   - AIサジェスト設定再読込を検証するウィジェットテストを追加し、保存後のUIリグレッションを防止
#   - ドキュメント/セットアップスクリプト/リリースノートをv2.2.5へ更新し、旧版ノートをdoc_archivesへ退避
# 2025-12-10: v2.2.4 - 設備/報告書リスティング + 報告書キャッシュ + 基本情報検索強化
#   - Equipment/Reports: フィルタ機能付きの共通リスティングテーブルを実装し、最新JSON出力をタブ内で即時ブラウズ可能に
#   - Reports: ReportCacheManagerとキャッシュモード切替UIを追加し、取得済みレコードの再利用や強制再取得を選択可能に
#   - Basic Info: 検索設定ダイアログを新設し、キーワード手動入力/機関ID+年度レンジからのキーワード生成・バッチ統合をサポート
#   - Equipment: 設備一覧スクレイパーと全件収集ロジックを導入し、設備ID収集と連続不在検知を自動化
# 2025-12-09: v2.2.3 - まとめXLSXの選択的出力・Explorer連携・テスト強化
#   - Basic Info: groupOrgnizationsごとに対象JSONを選べる「プロジェクトファイル選択」ダイアログを追加し、既定/外部ファイルの個別制御を実装
#   - Basic Info: まとめXLSXを複数生成した場合に選択して開けるダイアログと、出力フォルダをエクスプローラーで開くショートカットボタンを追加
#   - テスト/開発: groupProject・subGroupsを含むダミーデータ一式とsummary用ユニットテストを拡充し、選択的分割のリグレッションを自動検証
# 2025-12-08: v2.2.2 - データエントリー統計共有とSTRUCTURED JSONコンテキスト更新
#   - data_entry_summaryヘルパーでshared1/2/3集計を標準化し、ポータルのファイル統計自動設定を実装
#   - DatasetContextCollectorがjson_from_structured_filesを生成し、AIテンプレート/AutoSettingが構造化JSONを扱えるように調整
#   - 共有ボタンとプレースホルダ置換に対応する単体/ウィジェットテストを追加
# 2025-12-07: v2.2.1 - テンプレート/装置チャンク永続化と整合性検証リリース
#   - Basic Info: テンプレート/装置チャンク保存先の事前生成とクリーンアップ処理を実装
#   - API: ページネーションヘルパーでチャンクファイル出力をサポート
#   - テスト: チャンク処理ユニットテストを追加し、リビジョン同期を更新
# 2025-12-06: v2.2.0 - メジャーアップデート（包括的改善リリース）
#   - Basic Info: サブグループ完全性チェック・プログレス表示改善・並列化対応
#   - AI機能: llm_model_nameプレースホルダ置換修正・AI CHECK安定化
#   - データセット: 関連データビルダー・JST時間表示・RDE存在確認
#   - 設定: UI整理・暗号化保存・ログレベルCLI・ウィンドウ位置ポリシー
#   - テスト: ユニットテスト拡充（458件全合格）・バグ修正多数
# 2025-12-06: v2.1.24 - サブグループ完全性チェック再取得・グループ選択ダイアログのUIスレッド固定
# 2025-12-04: v2.1.16 - AI CHECKボタン追加・結果ダイアログフォント改善・可読性向上
# 2025-12-03: v2.1.15 - AI応答JSON引用除去・MItree階層表示・プレースホルダ完全解決
# 2025-11-11: v2.0.3 - ログインUI完全簡素化・手動ログイン実行機能・トークン管理2ホスト固定
# 2025-11-08: v2.0.0 - PyQt5→PySide6完全移行（破壊的変更）・blob画像取得修復・JavaScript連携改善
# 2025-11-07: v1.20.0 - データポータル統合機能完全実装・JSON/画像アップロード・修正機能・ステータス管理
# 2025-10-31: v1.19.2 - ARIM報告書スクレイピング修正・AI拡張タブ検索補完機能強化
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

# Debug flag（環境変数で制御）
def _debug_enabled():
    """ARIM_PATH_DEBUG フラグをチェック"""
    return os.environ.get('ARIM_PATH_DEBUG', '').lower() in ('1', 'true', 'yes')

def _env_flag_true(var_name: str) -> bool:
    return os.environ.get(var_name, '').lower() in ('1', 'true', 'yes')


def _resolve_user_dir_root() -> str:
    """Compute the default USERDIRROOTPATH for Windows."""
    if sys.platform.startswith("win"):
        # {localappdata} ≒ 環境変数 %LOCALAPPDATA%
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "ARIM-RDE-TOOL")
    # 非Windowsは旧仕様に合わせる例
    return os.path.join(os.path.expanduser("~"), ".arim_rde_tool")


USERDIRROOTPATH = _resolve_user_dir_root()


def is_binary_execution():
    """バイナリ実行かソース実行かを判定"""
    if _env_flag_true('ARIM_FORCE_BINARY'):
        if _debug_enabled():
            logger.debug('[PATH_DEBUG] is_binary_execution forced via ARIM_FORCE_BINARY=1')
        return True
    if _env_flag_true('ARIM_FORCE_SOURCE'):
        if _debug_enabled():
            logger.debug('[PATH_DEBUG] is_binary_execution forced via ARIM_FORCE_SOURCE=1')
        return False
    frozen = getattr(sys, 'frozen', False)
    if frozen and _debug_enabled():
        logger.debug('[PATH_DEBUG] sys.frozen detected -> binary execution')
    if hasattr(sys, '_MEIPASS') and _debug_enabled():
        logger.debug('[PATH_DEBUG] sys._MEIPASS detected -> binary execution')
    return frozen or hasattr(sys, '_MEIPASS')

def get_base_dir():
    """
    実行環境に応じた基準ディレクトリを取得（CWD非依存）
    - ソース実行時: メインソースファイル（arim_rde_tool.py）を基準
    - バイナリ実行時: ユーザーディレクトリ配下の.arim_rde_toolを基準
    
    Returns:
        str: 基準ディレクトリの絶対パス
        
    Raises:
        RuntimeError: バイナリ実行時にユーザーディレクトリの作成に失敗した場合
    """
    if is_binary_execution():
        # バイナリ実行時: ユーザーディレクトリ配下に.arim_rde_toolフォルダを使用
        # これにより、Program Files等の書き込み保護されたディレクトリにインストールされても
        # config/input/outputフォルダへの書き込みが可能
        user_data_dir = USERDIRROOTPATH
        
        # ディレクトリが存在しない場合は作成
        try:
            os.makedirs(user_data_dir, exist_ok=True)
            if _debug_enabled():
                logger.debug(f"[PATH_DEBUG] get_base_dir (binary): {user_data_dir}")
            return user_data_dir
        except (OSError, PermissionError) as e:
            # エラー: ユーザーディレクトリへの書き込みが失敗 → ダイアログ表示して中止
            error_msg = f"Failed to create user data directory: {e}\n\nPath: {user_data_dir}"
            logger.critical(error_msg)
            # GUI表示が可能な場合はダイアログ表示
            try:
                from PySide6.QtWidgets import QMessageBox, QApplication
                app = QApplication.instance()
                if app:
                    QMessageBox.critical(None, "ARIM RDE Tool - Critical Error", 
                        f"ユーザーディレクトリの作成に失敗しました。\n\n{error_msg}\n\nアプリケーションを終了します。")
            except Exception as gui_error:
                logger.error(f"Failed to show dialog: {gui_error}")
            # フォールバックなし：エラー送出
            raise RuntimeError(error_msg)
    else:
        # ソース実行時: メインソースファイル（arim_rde_tool.py）のディレクトリの親
        # src/config/common.py -> src -> project_root（arim_rde_tool.pyの親）
        src_dir = _get_src_dir_for_source_execution()  # src
        project_root = os.path.dirname(src_dir)  # project_root
        if _debug_enabled():
            logger.debug(f"[PATH_DEBUG] get_base_dir (source): {project_root}")
        return project_root

def get_static_resource_path(relative_path):
    """
    静的リソースファイルのパスを取得
    - ソース実行時: src/相対パスで参照（testsは例外でproject_root/testsを参照）
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
        # ソース実行時
        # testsディレクトリは特別扱い（project_root直下）
        if path_parts[0] == 'tests':
            return os.path.join(get_base_dir(), *path_parts)
        else:
            # その他のリソースはsrc配下
            src_dir = _get_src_dir_for_source_execution()
            return os.path.join(src_dir, *path_parts)

def get_dynamic_file_path(relative_path):
    """
    動的フォルダ（input/output）のパスを取得
    - ソース実行時: project_root/相対パスで参照
    - バイナリ実行時: ユーザーディレクトリ（~/.arim_rde_tool）配下で参照
    
    Args:
        relative_path (str): 動的フォルダへの相対パス（例: "input/data.xlsx"）
    
    Returns:
        str: 動的ファイルの絶対パス
    """
    # パスセパレータを正規化
    path_parts = relative_path.replace('/', os.sep).replace('\\', os.sep).split(os.sep)
    result = os.path.join(get_base_dir(), *path_parts)
    if _debug_enabled():
        logger.debug(f"[PATH_DEBUG] get_dynamic_file_path: {relative_path} -> {result}")
    return result

# ディレクトリ自動作成とパス定義

# 基準ディレクトリの取得
BASE_DIR = get_base_dir()

# 入力・出力・設定ディレクトリの定義
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
DATASET_JSON_CHUNKS_DIR = get_dynamic_file_path('output/rde/data/datasetJsonChunks')
TEMPLATE_JSON_CHUNKS_DIR = get_dynamic_file_path('output/rde/data/templateJsonChunks')
INSTRUMENT_JSON_CHUNKS_DIR = get_dynamic_file_path('output/rde/data/instrumentJsonChunks')

# ディレクトリの初期化フラグ
_directories_initialized = False

def initialize_directories():
    """
    必要なディレクトリを初期化する（遅延初期化）
    アプリケーション起動時に1度だけ呼び出される
    """
    global _directories_initialized
    if _directories_initialized:
        return
    
    # 基本ディレクトリの作成
    required_dirs = [
        INPUT_DIR,
        OUTPUT_DIR,
        OUTPUT_LOG_DIR,
        HIDDEN_DIR,
        CONFIG_DIR,
        DATASET_JSON_CHUNKS_DIR,
        TEMPLATE_JSON_CHUNKS_DIR,
        INSTRUMENT_JSON_CHUNKS_DIR,
    ]

    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
    
    _directories_initialized = True

def ensure_directory_exists(dir_path: str) -> str:
    """
    ディレクトリが存在しない場合は作成する
    
    Args:
        dir_path: ディレクトリパス
    
    Returns:
        ディレクトリパス（そのまま返す）
    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    
    # パス検証: ディレクトリがベースディレクトリ配下にあるかチェック（デバッグ用）
    if _debug_enabled():
        try:
            base = os.path.normpath(get_base_dir())
            normalized = os.path.normpath(dir_path)
            if not normalized.startswith(base):
                logger.warning(f"[PATH_DEBUG] WARNING: Directory escapes base_dir: base={base}, dir={normalized}")
            else:
                logger.debug(f"[PATH_DEBUG] ensure_directory_exists: {dir_path} OK")
        except Exception as e:
            logger.error(f"[PATH_DEBUG] Path validation error: {e}")
    
    return dir_path

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
# v2.0.3: bearer_token.txt廃止、bearer_tokens.jsonのみ使用
BEARER_TOKENS_FILE = os.path.join(HIDDEN_DIR, 'bearer_tokens.json')  # 複数ホスト対応（統一形式）

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
GROUP_JSON_PATH = get_dynamic_file_path('output/rde/data/group.json')
GROUP_PROJECT_DIR = get_dynamic_file_path('output/rde/data/groupProject')
GROUP_ORGNIZATION_DIR = get_dynamic_file_path('output/rde/data/groupOrgnizations')  # 仕様上のスペルを維持
SUBGROUP_DETAILS_DIR = get_dynamic_file_path('output/rde/data/subGroups')
LEGACY_SUBGROUP_DETAILS_DIR = get_dynamic_file_path('output/rde/data/subgroups')  # 互換目的
SUBGROUP_REL_DETAILS_DIR = get_dynamic_file_path('output/rde/data/subGroupsAncestors')
DATASET_JSON_PATH = get_dynamic_file_path('output/rde/data/dataset.json')
INFO_JSON_PATH = get_dynamic_file_path('output/rde/data/info.json')
SELF_JSON_PATH = get_dynamic_file_path('output/rde/data/self.json')
SUBGROUP_JSON_PATH = get_dynamic_file_path('output/rde/data/subGroup.json')
GROUP_SELECTION_HISTORY_FILE = get_dynamic_file_path('output/.private/group_selection_history.json')
TEMPLATE_JSON_PATH = get_dynamic_file_path('output/rde/data/template.json')
INSTRUMENTS_JSON_PATH = get_dynamic_file_path('output/rde/data/instruments.json')
LICENSES_JSON_PATH = get_dynamic_file_path('output/rde/data/licenses.json')
INSTRUMENT_TYPE_JSON_PATH = get_dynamic_file_path('output/rde/data/instrumentType.json')
ORGANIZATION_JSON_PATH = get_dynamic_file_path('output/rde/data/organization.json')
GROUP_DETAIL_JSON_PATH = get_dynamic_file_path('output/rde/data/groupDetail.json')
DATA_ENTRY_DIR = get_dynamic_file_path('output/rde/data/dataEntry')
INVOICE_DIR = get_dynamic_file_path('output/rde/data/invoice')

# 画像ディレクトリ（動的生成）
DYNAMIC_IMAGE_DIR = get_dynamic_file_path('output/images')
PROXY_IMAGE_DIR = get_dynamic_file_path('output/proxy_images')

# 検索結果ディレクトリ
SEARCH_RESULTS_DIR = get_dynamic_file_path('output/search_results')

# 動的ディレクトリは使用時に ensure_directory_exists() で作成される
        
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

def save_bearer_token(token, host: str = 'rde.nims.go.jp') -> bool:
    """
    Bearer Tokenを保存（複数ホスト対応）
    
    Args:
        token: 保存するBearerトークン（文字列 or TokenManager形式の辞書）
        host: ホスト名（例: 'rde.nims.go.jp', 'rde-material.nims.go.jp'）
    
    Returns:
        bool: 保存成功時True
    
    Note:
        v2.1.0: TokenManager形式（辞書）と従来形式（文字列）の両方に対応
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        
        # TokenManager形式（辞書）の場合はaccess_tokenを抽出
        if isinstance(token, dict):
            access_token = token.get('access_token', '')
            token_preview = access_token[:20] if access_token else 'N/A'
        else:
            access_token = token
            token_preview = token[:20] if token else 'N/A'
        
        # 既存のトークンを読み込み
        logger.debug(f"[TOKEN-SAVE] 既存トークンを読み込み: {BEARER_TOKENS_FILE}")
        logger.debug("保存開始 - host=%s, token=%s...", host, token_preview)
        tokens = load_all_bearer_tokens()
        logger.debug("既存トークン数: %s, ホスト: %s", len(tokens), list(tokens.keys()))
        
        # 新しいトークンを追加
        tokens[host] = token
        logger.info(f"[TOKEN-SAVE] トークンを追加: host={host}, token={token_preview}...")
        logger.debug("追加後トークン数: %s, ホスト: %s", len(tokens), list(tokens.keys()))
        
        # JSON形式で保存
        logger.debug(f"[TOKEN-SAVE] JSON形式で保存: {BEARER_TOKENS_FILE}")
        with open(BEARER_TOKENS_FILE, 'w', encoding='utf-8') as f:
            _json.dump(tokens, f, indent=2, ensure_ascii=False)
        logger.info(f"[TOKEN-SAVE] JSON保存完了: {len(tokens)}個のトークン")
        logger.debug("JSON保存完了: %s", BEARER_TOKENS_FILE)
        
        # 保存後の確認
        saved_tokens = load_all_bearer_tokens()
        logger.debug("保存確認 - ホスト数: %s, ホスト: %s", len(saved_tokens), list(saved_tokens.keys()))
        for saved_host, saved_token in saved_tokens.items():
            if isinstance(saved_token, dict):
                token_str = saved_token.get('access_token', '')
                logger.debug("%s: %s... (TokenManager形式)", saved_host, token_str[:20])
            else:
                logger.debug("%s: %s...", saved_host, saved_token[:20])
        
        # v2.0.3: レガシーファイル（bearer_token.txt）への保存は廃止
        
        return True
    except Exception as e:
        logger.debug("Bearer Token保存エラー (%s): %s", host, e)
        logger.error(f"Bearer Token保存エラー ({host}): {e}")
        return False

def load_bearer_token(host: str = 'rde.nims.go.jp') -> Optional[str]:
    """
    指定ホストのBearer Tokenを取得
    
    Args:
        host: ホスト名（例: 'rde.nims.go.jp', 'rde-material.nims.go.jp'）
    
    Returns:
        str: トークン文字列、存在しない場合None
    
    Note:
        v2.1.0: TokenManager形式（辞書）と従来形式（文字列）の両方に対応
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        
        logger.debug("トークン読み込み開始 - host=%s", host)
        logger.debug(f"[TOKEN-LOAD] トークン読み込み開始: host={host}")
        
        # 新形式のJSONファイルから読み込み
        if os.path.exists(BEARER_TOKENS_FILE):
            logger.debug(f"[TOKEN-LOAD] JSON形式トークンファイル読み込み: {BEARER_TOKENS_FILE}")
            logger.debug("JSONファイルから読み込み中...")
            with open(BEARER_TOKENS_FILE, 'r', encoding='utf-8') as f:
                tokens = _json.load(f)
                logger.debug("ファイル内のホスト数: %s, ホスト: %s", len(tokens), list(tokens.keys()))
                if host in tokens:
                    token_data = tokens[host]
                    
                    # TokenManager形式（辞書）の場合はaccess_tokenを抽出
                    if isinstance(token_data, dict):
                        access_token = token_data.get('access_token', '')
                        if access_token:
                            logger.info(f"[TOKEN-LOAD] トークン読み込み成功 ({host}): {access_token[:20]}... (TokenManager形式)")
                            logger.debug("トークン取得成功 (TokenManager形式) - host=%s, token=%s...", host, access_token[:20])
                            return access_token
                        else:
                            logger.warning(f"[TOKEN-LOAD] TokenManager形式だがaccess_tokenが空 ({host})")
                            logger.debug("access_token欠落")
                    else:
                        # 従来形式（文字列）
                        logger.info(f"[TOKEN-LOAD] トークン読み込み成功 ({host}): {token_data[:20]}... (従来形式)")
                        logger.debug("トークン取得成功 (従来形式) - host=%s, token=%s...", host, token_data[:20])
                        return token_data
                else:
                    logger.warning(f"[TOKEN-LOAD] ホスト {host} のトークンが見つかりません")
                    logger.debug("指定ホストのトークンなし - host=%s", host)
        else:
            logger.debug(f"[TOKEN-LOAD] JSON形式トークンファイルが存在しません: {BEARER_TOKENS_FILE}")
            logger.debug("JSONファイルが存在しません")
        
        # v2.0.3: レガシーファイル（bearer_token.txt）からの読み込みは廃止
        
        logger.warning(f"[TOKEN-LOAD] トークンが見つかりません ({host})")
        logger.debug("トークンが見つかりませんでした - host=%s", host)
        return None
    except Exception as e:
        logger.debug("Bearer Token読み込みエラー (%s): %s", host, e)
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
        logger.error("Bearer Token一括読み込みエラー: %s", e)
        return {}

def delete_bearer_token(host: str = 'rde.nims.go.jp') -> bool:
    """
    指定ホストのBearer Tokenを削除
    
    Args:
        host: ホスト名（例: 'rde.nims.go.jp', 'rde-material.nims.go.jp'）
    
    Returns:
        bool: 削除成功時True（元々存在しない場合もTrue）
    
    Note:
        v2.0.6: ログインボタン押下時のトークン無効化に使用
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        
        logger.debug(f"[TOKEN-DELETE] トークン削除開始: host={host}")
        
        # 既存のトークンを読み込み
        if not os.path.exists(BEARER_TOKENS_FILE):
            logger.info(f"[TOKEN-DELETE] トークンファイルが存在しません（削除不要）")
            return True
        
        with open(BEARER_TOKENS_FILE, 'r', encoding='utf-8') as f:
            tokens = _json.load(f)
        
        # 指定ホストのトークンを削除
        if host in tokens:
            del tokens[host]
            logger.info(f"[TOKEN-DELETE] トークンを削除: host={host}")
        else:
            logger.info(f"[TOKEN-DELETE] 削除対象のトークンが存在しません: host={host}")
        
        # JSON形式で保存（空になった場合も保存）
        with open(BEARER_TOKENS_FILE, 'w', encoding='utf-8') as f:
            _json.dump(tokens, f, indent=2, ensure_ascii=False)
        logger.info(f"[TOKEN-DELETE] 削除後のトークン保存完了: {len(tokens)}個")
        
        return True
    except Exception as e:
        logger.error(f"[TOKEN-DELETE] Bearer Token削除エラー ({host}): {e}", exc_info=True)
        return False

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
                logger.debug("Material token for %s", host)
                return token
            else:
                logger.warning(f"[TOKEN-SELECT] Material token not found, falling back to RDE token")
                logger.debug("Material token not found, using RDE token")
    
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
                logger.debug("RDE token for %s", host)
                return token
    
    # 3. デフォルトトークンは送信先を限定
    # セキュリティ上、未知の外部ドメインへRDEトークンを送らない。
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        netloc = (parsed.netloc or "").lower()
    except Exception:
        netloc = ""

    if netloc.endswith(".nims.go.jp") or netloc == "nims.go.jp":
        logger.warning(f"[TOKEN-SELECT] No specific host matched, using default RDE token for: {url[:50]}...")
        logger.debug("Default RDE token for: %s...", url[:50])
        return load_bearer_token('rde.nims.go.jp')

    logger.debug(f"[TOKEN-SELECT] No bearer token for external host: {url[:50]}...")
    return None

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
            logger.debug("デフォルトconfig作成: %s", network_json_path)
        except Exception as e:
            logger.debug("network.json作成失敗: %s", e)
    
    # network.yaml の作成
    network_yaml_path = os.path.join(CONFIG_DIR, 'network.yaml')
    if not os.path.exists(network_yaml_path):
        try:
            with open(network_yaml_path, 'w', encoding='utf-8') as f:
                f.write(network_yaml_content)
            logger.debug("デフォルトconfig作成: %s", network_yaml_path)
        except Exception as e:
            logger.debug("network.yaml作成失敗: %s", e)

# 起動時に設定ファイルを自動作成
create_default_config_files()
DEBUG_LOG_FULL_ARGS = False  # Trueで引数全文、Falseで100文字に切り詰め