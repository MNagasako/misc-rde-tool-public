"""
データポータル JSONアップローダー

JSONファイルをデータポータルサイトにアップロードする機能を提供
"""

import json
import logging
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, Iterable

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

    @staticmethod
    def is_zip_file(path: str) -> Tuple[bool, str]:
        """ZIPファイルかどうかを簡易チェックする。

        - 拡張子が .zip
        - 先頭2バイトが PK

        Returns:
            (ok, message)
        """

        try:
            p = Path(path)
            if not p.exists():
                return False, "ファイルが存在しません"
            if p.suffix.lower() != ".zip":
                return False, "ZIP形式のみアップロード可能です（拡張子が .zip ではありません）"
            with open(p, "rb") as fh:
                sig = fh.read(2)
            if sig != b"PK":
                return False, "ZIP形式のみアップロード可能です（ZIPシグネチャが一致しません）"
            return True, "OK"
        except Exception as e:
            return False, f"ZIPファイル検証に失敗しました: {e}"

    @staticmethod
    def _contains_any(text: str, phrases: Iterable[str], *, strict: bool) -> bool:
        """テキストがフレーズにマッチするか。

        strict=False: 部分一致
        strict=True : 完全一致
        """

        t = (text or "")
        if strict:
            return any(t == (p or "") for p in phrases)
        return any((p or "") in t for p in phrases)

    @classmethod
    def parse_contents_upload_result(
        cls,
        html: str,
        *,
        strict_match: bool = False,
    ) -> Tuple[bool, str]:
        """contents_upload のレスポンスHTMLから成功/失敗を推定する。

        要件:
        - 基本は「部分一致」で判定
        - ただし短すぎる条件は避ける
        - 将来「完全一致」に切替できるように strict_match を用意

        NOTE:
        strict_match=True に切替えると完全一致になります。
        UI側の要件により、現状は部分一致運用をデフォルトにしています。
        """

        text = html or ""

        # 成功（上書き含む）
        success_phrases = [
            "アップロード（上書き）しました。",
            "アップロード（上書き）しました",
            "アップロードしました。",
            "アップロードしました",
        ]

        # 失敗（代表的なもの）
        error_phrases = [
            "拡張子はzipです",
            "アップロードできるファイルの拡張子はzip",
            "ファイルが選択されていません",
            "エラー",
            "失敗",
        ]

        if cls._contains_any(text, success_phrases, strict=strict_match):
            return True, "アップロード成功"

        if cls._contains_any(text, error_phrases, strict=False):
            # 失敗理由はUIログ用に先頭を返す（過度な短文化は避ける）
            preview = text
            preview = preview.replace("\r\n", "\n")
            preview = preview[:500]
            return False, f"アップロード失敗の可能性: {preview}"

        # 判定不能は成功扱いにせず、UIに確認させる
        preview = text.replace("\r\n", "\n")[:500]
        return False, f"アップロード結果を判定できません: {preview}"

    def upload_contents_zip(self, t_code: str, zip_file_path: str) -> Tuple[bool, str]:
        """データポータルへコンテンツZIPをアップロード（mode2=contents_upload）。

        既存ファイルがある場合でも上書きアップロード可能（ポータル側仕様）。
        """

        ok, msg = self.is_zip_file(zip_file_path)
        if not ok:
            return False, msg

        t_code_text = str(t_code or "").strip()
        if not t_code_text:
            return False, "t_code が未設定です"

        zip_path = Path(zip_file_path)

        try:
            logger.info(f"ZIPアップロード開始: t_code={t_code_text}, file={zip_path.name}")

            # Step 0: ログイン（セッション確立）
            login_success, login_message = self.client.login()
            if not login_success:
                return False, f"ログイン失敗: {login_message}"

            # Step 1: 初期ページ取得
            ok, resp = self.client.get("main.php", params={"mode": "theme"})
            if not ok or not hasattr(resp, "text"):
                return False, "初期ページ取得失敗"
            self._save_debug_response("contents_step1_theme", resp.text)

            # Step 2: アップロード画面へ遷移（application/x-www-form-urlencoded）
            data_open = {
                "mode": "theme",
                "mode2": "contents_upload",
                "t_code": t_code_text,
                "keyword": "",
                "search_inst": "",
                "search_license_level": "",
                "search_status": "",
                "page": "1",
            }
            ok, resp = self.client.post("main.php", data=data_open)
            if not ok or not hasattr(resp, "text"):
                return False, "アップロード画面遷移失敗"
            self._save_debug_response("contents_step2_open", resp.text)

            # Step 3: multipart/form-data でZIP送信
            with open(zip_path, "rb") as fh:
                files = {
                    "contents_file": (zip_path.name, fh, "application/x-zip-compressed"),
                }
                data_upload = {
                    "mode": "theme",
                    "mode2": "contents_upload",
                    "mode3": "rec",
                    "t_code": t_code_text,
                    "keyword": "",
                    "search_inst": "",
                    "search_license_level": "",
                    "search_status": "",
                    "page": "1",
                }

                ok, resp = self.client.post("main.php", data=data_upload, files=files)
                if not ok or not hasattr(resp, "text"):
                    return False, "ZIPアップロード失敗"
                self._save_debug_response("contents_step3_upload", resp.text)

                # 成功判定（部分一致）
                # NOTE: 将来、完全一致に切替する場合は strict_match=True にする
                success, message = self.parse_contents_upload_result(resp.text, strict_match=False)
                return success, message

        except Exception as e:
            logger.error(f"ZIPアップロード処理でエラー: {e}")
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
