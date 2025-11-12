"""
データ登録ロジッククラス

既存のrun_data_register_logic関数をクラス形式でラップ
"""

import os
import json
import logging
from typing import List, Dict, Optional, Any
from qt_compat.widgets import QMessageBox

from . import data_register_logic as legacy_logic

logger = logging.getLogger(__name__)


class DataRegisterLogic:
    """データ登録ロジッククラス"""
    
    def __init__(self):
        self.logger = logger
    
    def _get_bearer_token(self) -> Optional[str]:
        """Bearerトークンを取得（v2.0.3: JSON形式のみ）"""
        try:
            from config.common import load_bearer_token
            
            token = load_bearer_token('rde.nims.go.jp')
            return token if token else None
                
        except Exception as e:
            self.logger.error(f"Bearerトークン取得エラー: {e}")
            return None
    
    def run_data_register_logic(self, dataset_id: str, upload_files: List[str], 
                               data_name: str = "", description: str = "",
                               experiment_id: str = "", reference_url: str = "",
                               tags: str = "", sample_mode: str = "new",
                               sample_id: Optional[str] = None, sample_name: str = "",
                               sample_description: str = "", sample_composition: str = "",
                               custom_values: Dict[str, Any] = None,
                               bearer_token: Optional[str] = None,
                               parent=None) -> bool:
        """
        データ登録処理を実行
        
        Args:
            dataset_id: データセットID
            upload_files: アップロードするファイルパス一覧
            data_name: データ名
            description: データ説明
            experiment_id: 実験ID
            reference_url: 参考URL
            tags: タグ
            sample_mode: 試料モード（new/existing/same_as_previous）
            sample_id: 既存試料ID
            sample_name: 試料名
            sample_description: 試料説明
            sample_composition: 試料組成
            custom_values: カスタム値
            bearer_token: Bearerトークン
            parent: 親ウィジェット
            
        Returns:
            bool: 成功時True、失敗時False
        """
        try:
            # dataset_info構築
            dataset_info = {
                "id": dataset_id,
                "attributes": {
                    "title": data_name or "データ登録",
                    "description": description
                }
            }
            
            # form_values構築
            form_values = {
                "data_name": data_name,
                "description": description,
                "experiment_id": experiment_id,
                "reference_url": reference_url,
                "tags": tags,
                "sample_mode": sample_mode,
                "sample_id": sample_id,
                "sample_name": sample_name,
                "sample_description": sample_description,
                "sample_composition": sample_composition
            }
            
            # カスタム値の設定（nullを含む可能性があるため適切に処理）
            if custom_values is not None:
                # custom_valuesを"custom"キーで設定し、direct mergeも行う
                form_values["custom"] = custom_values
                form_values["custom_values"] = custom_values  # フォールバック用
            
            # Bearerトークン取得（指定されていない場合）
            if not bearer_token:
                bearer_token = self._get_bearer_token()
                
                if not bearer_token:
                    self.logger.error("Bearerトークンが取得できません")
                    if parent:
                        QMessageBox.critical(parent, "認証エラー", "認証情報を取得できませんでした。\nログイン状態を確認してください。")
                    return False
            
            # 既存のrun_data_register_logic関数を呼び出し
            result = legacy_logic.run_data_register_logic(
                parent=parent,
                bearer_token=bearer_token,
                dataset_info=dataset_info,
                form_values=form_values,
                file_paths=upload_files,
                attachment_paths=None
            )
            
            return result is not None  # 成功時はNone以外が返される想定
            
        except Exception as e:
            self.logger.error(f"データ登録処理でエラーが発生しました: {e}")
            if parent:
                QMessageBox.critical(parent, "データ登録エラー", f"データ登録処理でエラーが発生しました:\n{str(e)}")
            return False
    
    def entry_data(self, **kwargs):
        """データエントリー作成（互換性用ラッパー）"""
        return self.run_data_register_logic(**kwargs)
    
    def upload_file(self, file_path: str, bearer_token: Optional[str] = None) -> Optional[str]:
        """
        ファイルアップロード処理
        
        Args:
            file_path: アップロードするファイルパス
            bearer_token: Bearerトークン
            
        Returns:
            str: アップロードID（失敗時はNone）
        """
        try:
            if not bearer_token:
                bearer_token = self._get_bearer_token()
                
                if not bearer_token:
                    self.logger.error("Bearerトークンが取得できません")
                    return None
            
            # 既存の個別ファイルアップロード関数があれば使用
            # ここでは簡略実装として、既存のロジックに依存
            # 実際の実装では個別ファイルアップロードAPIを直接呼び出す
            
            self.logger.info(f"ファイルアップロード開始: {file_path}")
            
            # 仮実装：ファイル名をIDとして返す（実際にはAPIを呼び出してIDを取得）
            return os.path.basename(file_path)
            
        except Exception as e:
            self.logger.error(f"ファイルアップロードでエラーが発生しました: {e}")
            return None
