"""
設定管理ロジック - ARIM RDE Tool
新構造対応: REFACTOR_PLAN_01.md準拠

主要機能:
- 設定ダイアログの起動
- プロキシ設定管理
- ネットワーク設定管理
- アプリケーション設定管理
"""

import logging
from typing import Optional, Any

# ログ設定
logger = logging.getLogger(__name__)

def run_settings_logic(parent=None, bearer_token=None):
    """
    設定ロジックのメイン関数
    旧構造との互換性を保持しつつ、新構造のUIを呼び出す
    
    Args:
        parent: 親ウィジェット
        bearer_token: 認証トークン
    """
    try:
        # 新構造のUI設定ダイアログを呼び出し
        from classes.config.ui.settings_dialog import run_settings_logic as ui_run_settings
        ui_run_settings(parent=parent, bearer_token=bearer_token)
        
    except ImportError as e:
        logger.error(f"設定UIのインポートに失敗: {e}")
        # フォールバック: エラーメッセージを表示
        try:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                parent, 
                "設定エラー", 
                f"設定画面の起動に失敗しました。\n\nエラー: {e}\n\n"
                "プロキシ設定は config/network.json を直接編集してください。"
            )
        except:
            print(f"[ERROR] 設定画面起動失敗: {e}")
            
    except Exception as e:
        logger.error(f"設定ロジック実行エラー: {e}")
        try:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(parent, "予期しないエラー", f"設定処理中にエラーが発生しました: {e}")
        except:
            print(f"[ERROR] 設定処理エラー: {e}")


def get_application_settings() -> dict:
    """アプリケーション設定を取得"""
    try:
        # デフォルト設定
        settings = {
            'ui': {
                'font_size': 'system',
                'theme': 'system', 
                'language': 'ja'
            },
            'network': {
                'http_timeout': 30,
                'webview_timeout': 60,
                'auto_proxy': True
            },
            'logging': {
                'level': 'INFO',
                'file_output': True,
                'console_output': True
            }
        }
        
        # 設定ファイルがあれば読み込み（今後の拡張用）
        try:
            from config.common import get_dynamic_file_path
            import json
            
            config_path = get_dynamic_file_path('config/app_settings.json')
            if config_path and config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_settings = json.load(f)
                    settings.update(user_settings)
                    
        except Exception as e:
            logger.debug(f"ユーザー設定ファイル読み込み失敗（デフォルト設定使用）: {e}")
            
        return settings
        
    except Exception as e:
        logger.error(f"アプリケーション設定取得エラー: {e}")
        return {}


def save_application_settings(settings: dict) -> bool:
    """アプリケーション設定を保存"""
    try:
        from config.common import get_dynamic_file_path
        import json
        
        config_path = get_dynamic_file_path('config/app_settings.json')
        if config_path:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            return True
            
    except Exception as e:
        logger.error(f"アプリケーション設定保存エラー: {e}")
        return False


def get_proxy_settings() -> dict:
    """プロキシ設定を取得"""
    try:
        from net.session_manager import get_proxy_config
        return get_proxy_config() or {}
    except Exception as e:
        logger.error(f"プロキシ設定取得エラー: {e}")
        return {}


def apply_proxy_settings(proxy_config: dict) -> bool:
    """プロキシ設定を適用"""
    try:
        from net.session_manager import save_proxy_config
        return save_proxy_config(proxy_config)
    except Exception as e:
        logger.error(f"プロキシ設定適用エラー: {e}")
        return False
