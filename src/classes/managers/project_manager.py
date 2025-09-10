"""
プロジェクト・課題管理クラス - ARIM RDE Tool v1.13.1
grantNumberの設定、検索、データ取得を管理
プロジェクト状態管理・データツリー操作機能
【注意】バージョン更新時はconfig/common.py のREVISIONも要確認
"""
import os
import json
import logging
from config.common import OUTPUT_DIR

logger = logging.getLogger("RDE_WebView")

class ProjectManager:
    """
    プロジェクト・課題管理クラス
    grantNumberの設定、検索、データ取得を管理
    """
    def __init__(self, browser, data_manager, datatree_manager):
        self.browser = browser
        self.data_manager = data_manager
        self.datatree_manager = datatree_manager
        self.grant_number = None
        self._current_image_grant_number = None
        
    def set_grant_number(self, grant_number):
        """grantNumberを設定し、必要な初期化を行う"""
        # grantNumberが変更された場合、前回の状態をクリア
        if hasattr(self, 'grant_number') and self.grant_number != grant_number:
            logger.info(f"[GRANT_CHANGE] grantNumber変更: {getattr(self, 'grant_number', 'None')} -> {grant_number}")
            # BLOB画像のハッシュ履歴をクリア（重複検出のリセット）
            if hasattr(self.browser, '_recent_blob_hashes'):
                self.browser._recent_blob_hashes.clear()
            # data_id毎の画像カウンタもクリア
            if hasattr(self.browser, '_data_id_image_counts'):
                self.browser._data_id_image_counts.clear()
            logger.debug("[GRANT_CHANGE] BLOB画像ハッシュ履歴と画像カウンタをクリアしました")
        
        self.grant_number = grant_number
        self.browser.grant_number = grant_number
        # 現在の画像取得用grantNumberを設定（混入防止）
        self._current_image_grant_number = grant_number
        self.browser._current_image_grant_number = grant_number
        logger.debug(f"[SINGLE] _current_image_grant_number を {grant_number} に設定")
        
    def process_grant_number(self, grant_number):
        """grantNumberの処理を実行"""
        try:
            # grantNumberを設定
            self.set_grant_number(grant_number)
            
            # データツリーに課題情報を追加
            self._add_grant_to_datatree(grant_number)
            
            # 検索・保存処理を実行
            self.browser.set_webview_message('課題情報検索中')
            logger.info(f"grantNumberを {grant_number} で検索します")
            
            # grantNumberでAPI検索し、検索結果を保存
            self.browser.search_and_save_result(grant_number=grant_number)
            
            # 検索結果からデータセット詳細を取得・保存
            logger.info(f"データセット詳細取得開始: {grant_number}")
            self.browser.fetch_and_save_multiple_datasets(grant_number=grant_number)
            logger.info(f"データセット詳細取得完了: {grant_number}")
            
            # 完了処理
            self.browser.set_webview_message('課題情報取得完了')
            logger.info(f"grantNumber {grant_number} の処理が完了しました")
            
            return True
            
        except Exception as e:
            logger.error(f"grantNumber処理中にエラーが発生: {e}")
            self.browser.set_webview_message(f'エラー: {e}')
            return False
            
    def _add_grant_to_datatree(self, grant_number):
        """データツリーにgrant情報を追加"""
        search_result_path = os.path.join(OUTPUT_DIR, "search_results", f"{grant_number}.json")
        grant_name = None
        
        if os.path.exists(search_result_path):
            try:
                with open(search_result_path, encoding="utf-8") as f:
                    data = json.load(f)
                    if "data" in data and len(data["data"]) > 0:
                        grant_name = data["data"][0]["attributes"].get("subjectTitle") or data["data"][0]["attributes"].get("name")
            except Exception as e:
                logger.warning(f"grant_number/name抽出失敗: {e}")
                
        if not grant_name:
            grant_name = "(未取得)"
            
        # type_name="grant" を明示的に渡す
        self.datatree_manager.add_or_update_grant(grant_number, grant_name, type_name="grant")
        
    def get_current_grant_number(self):
        """現在のgrantNumberを取得"""
        return self.grant_number
        
    def get_current_image_grant_number(self):
        """現在の画像取得用grantNumberを取得"""
        return self._current_image_grant_number
