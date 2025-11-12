"""
トークン・認証情報自動削除ユーティリティ

セキュリティのため、output/.private ディレクトリの内容を
起動時と終了時に自動削除します。

v2.0.4: 常に有効化（機微情報保護のため）
デバッグモード時は追加のログ出力を行います。
"""

import os
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def is_debug_skip_mode() -> bool:
    """
    デバッグモード（ログインスキップ）が有効かチェック
    
    Returns:
        bool: DEBUG_SKIP_LOGIN_CHECK環境変数が有効な場合True
    """
    debug_skip = os.environ.get('DEBUG_SKIP_LOGIN_CHECK', '').lower()
    return debug_skip in ('1', 'true', 'yes')


def clear_private_directory():
    """
    output/.private ディレクトリの内容をクリア
    
    セキュリティのため、トークンや認証情報を削除します。
    ディレクトリ自体は削除せず、中身のみを削除します。
    
    v2.0.4: 常に実行（デバッグモードに関係なく）
    
    Note:
        削除対象:
        - bearer_tokens.json (全ホストのトークン)
        - creds.enc.json (暗号化認証情報)
        - .cookies_rde.txt (Cookie)
        - その他の一時ファイル・サブディレクトリ
    """
    from config.common import HIDDEN_DIR
    
    if not os.path.exists(HIDDEN_DIR):
        logger.debug(f"[CLEANUP] {HIDDEN_DIR} が存在しません（スキップ）")
        return
    
    try:
        deleted_count = 0
        # ディレクトリ内のファイルとサブディレクトリを削除
        for item in Path(HIDDEN_DIR).iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    deleted_count += 1
                    logger.debug(f"[CLEANUP] ファイル削除: {item.name}")
                elif item.is_dir():
                    shutil.rmtree(item)
                    deleted_count += 1
                    logger.debug(f"[CLEANUP] ディレクトリ削除: {item.name}")
            except Exception as e:
                logger.warning(f"[CLEANUP] 削除失敗: {item.name} - {e}")
        
        if deleted_count > 0:
            logger.info(f"[CLEANUP] {HIDDEN_DIR} の内容をクリアしました（{deleted_count}件）")
        else:
            logger.debug(f"[CLEANUP] {HIDDEN_DIR} は既に空でした")
        
    except Exception as e:
        logger.error(f"[CLEANUP] クリーンアップエラー: {e}", exc_info=True)


def cleanup_on_startup():
    """
    起動時のクリーンアップ処理
    
    v2.0.4: 常に実行（セキュリティのため）
    output/.private の内容を自動削除します。
    """
    debug_mode = is_debug_skip_mode()
    
    if debug_mode:
        logger.warning("[CLEANUP] デバッグモード起動 - トークン・認証情報をクリア")
        print("=" * 80)
        print("[CLEANUP] デバッグモード起動検出")
        print("[CLEANUP] 既存のトークン・認証情報をクリアします...")
        print("=" * 80)
    else:
        logger.info("[CLEANUP] 起動時クリーンアップ - トークン・認証情報を削除")
    
    clear_private_directory()
    
    if debug_mode:
        print("[CLEANUP] クリーンアップ完了")
        print("=" * 80)


def cleanup_on_exit():
    """
    終了時のクリーンアップ処理
    
    v2.0.4: 常に実行（セキュリティのため）
    output/.private の内容を自動削除します。
    """
    debug_mode = is_debug_skip_mode()
    
    if debug_mode:
        logger.warning("[CLEANUP] デバッグモード終了 - トークン・認証情報をクリア")
        print("=" * 80)
        print("[CLEANUP] アプリケーション終了 - デバッグモード")
        print("[CLEANUP] トークン・認証情報をクリアします...")
        print("=" * 80)
    else:
        logger.info("[CLEANUP] 終了時クリーンアップ - トークン・認証情報を削除")
    
    clear_private_directory()
    
    if debug_mode:
        print("[CLEANUP] クリーンアップ完了")
        print("=" * 80)


def get_debug_status_message() -> str:
    """
    デバッグモードのステータスメッセージを取得
    
    Returns:
        str: デバッグモードが有効な場合は警告メッセージ、無効な場合は空文字列
    
    Note:
        v2.0.4: トークンクリーンアップは全モードで実行されるため、
        メッセージからは「トークン自動クリア」の記述を削除
    """
    if is_debug_skip_mode():
        return "🔧 デバッグモード（ログインチェックスキップ）"
    return ""
