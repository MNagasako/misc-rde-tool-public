"""
データポータル JSONアップローダー

JSONファイルをデータポータルサイトにアップロードする機能を提供
"""

import json
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

from classes.managers.log_manager import get_logger
from .portal_client import PortalClient

logger = get_logger("DataPortal.Uploader")


class Uploader:
    """
    JSONアップローダークラス
    
    機能:
    - JSONファイルのアップロード
    - アップロード確認ステップ
    - 最終登録処理
    """
    
    def __init__(self, client: PortalClient):
        """
        初期化
        
        Args:
            client: PortalClientインスタンス
        """
        self.client = client
    
    def _save_debug_response(self, step_name: str, response_text: str):
        """
        デバッグ用にレスポンスを保存
        
        Args:
            step_name: ステップ名
            response_text: レスポンステキスト
        """
        try:
            from config.common import get_dynamic_file_path
            import os
            from datetime import datetime
            
            debug_dir = get_dynamic_file_path("output/data_portal_debug")
            os.makedirs(debug_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{step_name}_{timestamp}.html"
            filepath = os.path.join(debug_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(response_text)
            
            logger.info(f"デバッグレスポンス保存: {filepath}")
        except Exception as e:
            logger.warning(f"デバッグレスポンス保存失敗: {e}")
    
    def upload_json_file(self, json_file_path: str, dry_run: bool = False) -> Tuple[bool, str]:
        """
        JSONファイルをアップロード
        
        Args:
            json_file_path: アップロードするJSONファイルのパス
        
        Returns:
            Tuple[bool, str]: (成功フラグ, メッセージ)
        """
        json_path = Path(json_file_path)
        
        if not json_path.exists():
            logger.error(f"JSONファイルが見つかりません: {json_file_path}")
            return False, f"ファイルが存在しません: {json_file_path}"
        
        # JSONファイルの検証
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            logger.info(f"JSON検証成功: {json_path.name}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析エラー: {e}")
            return False, f"JSON解析エラー: {e}"
        except Exception as e:
            logger.error(f"ファイル読み込みエラー: {e}")
            return False, f"ファイル読み込みエラー: {e}"
        
        try:
            logger.info(f"JSONアップロード開始: {json_path.name}")
            
            # Step 0: ログイン実行（必須）
            logger.info("Step 0: ログイン実行...")
            # 毎回ログインを実行（セッション確立のため）
            login_success, login_message = self.client.login()
            if not login_success:
                return False, f"ログイン失敗: {login_message}"
            logger.info("✅ ログイン成功")
            
            # Step 1: 初期ページ取得（セッション確認）
            logger.info("Step 1: 初期ページ取得...")
            success, response = self.client.get("main.php", params={"mode": "theme"})
            if not success:
                return False, f"初期ページ取得失敗: {response}"
            
            # Step1のレスポンスを保存
            self._save_debug_response("step1_initial_page", response.text)
            logger.info("✅ 初期ページ取得成功")
            
            # Step 2: ファイルアップロード確認段階
            logger.info("Step 2: ファイルアップロード確認...")
            success, response_or_message = self._upload_file_confirmation(json_path)
            if not success:
                return False, f"ファイルアップロード確認失敗: {response_or_message}"
            
            # レスポンスを保存（デバッグ用）
            if hasattr(response_or_message, 'text'):
                self._save_debug_response("step2_upload_confirmation", response_or_message.text)
            
            # Step 3: 最終登録（dry_run時はスキップ）
            if dry_run:
                logger.info("Step 3: 最終登録はdry-runのためスキップします")
                return True, "確認画面まで到達（dry-runで登録は未実行）"
            else:
                logger.info("Step 3: 最終登録...")
                success, response_or_message = self._complete_upload(json_path)
                if not success:
                    return False, f"最終登録失敗: {response_or_message}"
                
                # レスポンスを保存（デバッグ用）
                if hasattr(response_or_message, 'text'):
                    self._save_debug_response("step3_complete_upload", response_or_message.text)
                
                logger.info("✅ JSONファイルアップロード完了!")
                return True, "アップロード成功"
            
        except Exception as e:
            logger.error(f"アップロード処理でエラー: {e}")
            return False, str(e)
    
    def _upload_file_confirmation(self, json_path: Path) -> Tuple[bool, Any]:
        """
        ファイルアップロード確認段階
        
        Args:
            json_path: JSONファイルパス
        
        Returns:
            Tuple[bool, Any]: (成功フラグ, レスポンスまたはエラーメッセージ)
        """
        try:
            with open(json_path, 'rb') as f:
                files = {
                    'upload_json_file': (json_path.name, f, 'application/json')
                }
                
                data = {
                    'mode': 'theme',
                    'mode2': 'json_upload',
                    'mode3': 'conf',
                    'keyword': '',
                    'search_inst': '',
                    'search_license_level': '',
                    'search_status': '',
                    'page': '1'
                }
                
                logger.info(f"ファイルアップロード中: {json_path.name} ({json_path.stat().st_size} bytes)")
                logger.info(f"POSTパラメータ: {data}")
                
                success, response = self.client.post("main.php", data=data, files=files)
                
                if not success:
                    return False, response
                
                # レスポンス内容をチェック
                response_text = response.text
                logger.info(f"Step2レスポンス長: {len(response_text)} bytes")
                
                # エラーメッセージをチェック
                if "ファイルが選択されていません" in response_text:
                    logger.error("エラー: ファイルが選択されていません")
                    return False, "ファイルが選択されていません"
                elif "エラー" in response_text:
                    logger.error(f"エラー応答を検出: {response_text[:500]}")
                    return False, f"サーバーエラー: {response_text[:200]}"
                elif "アップロード" in response_text and "確認" in response_text:
                    logger.info("✅ ファイルアップロード確認画面に到達")
                    return True, response
                else:
                    logger.warning(f"予期しない応答（続行）: {response_text[:200]}...")
                    return True, response
                    
        except Exception as e:
            logger.error(f"ファイルアップロード確認エラー: {e}")
            return False, str(e)
    
    def _complete_upload(self, json_path: Path) -> Tuple[bool, Any]:
        """
        最終登録処理
        
        Args:
            json_path: JSONファイルパス
        
        Returns:
            Tuple[bool, Any]: (成功フラグ, レスポンスまたはエラーメッセージ)
        """
        try:
            data = {
                'mode': 'theme',
                'mode2': 'json_upload',
                'mode3': 'rec',
                'json_filename': json_path.name,
                'keyword': '',
                'search_inst': '',
                'search_license_level': '',
                'search_status': '',
                'page': '1'
            }
            
            logger.info(f"最終登録処理中: {json_path.name}")
            logger.info(f"POSTパラメータ: {data}")
            
            success, response = self.client.post("main.php", data=data)
            
            if not success:
                return False, response
            
            # レスポンス内容をチェック
            response_text = response.text
            logger.info(f"Step3レスポンス長: {len(response_text)} bytes")
            
            if "登録しました" in response_text or "登録完了" in response_text:
                logger.info("✅ 最終登録成功（成功メッセージ確認）")
                return True, response
            elif "エラー" in response_text or "失敗" in response_text:
                logger.error(f"❌ 登録エラー: {response_text[:500]}")
                return False, f"登録エラー: {response_text[:200]}"
            else:
                logger.warning(f"⚠️ 予期しない応答（成功とみなす）: {response_text[:200]}...")
                return True, response
                
        except Exception as e:
            logger.error(f"最終登録エラー: {e}")
            return False, str(e)
