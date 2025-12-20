"""
ユーザー情報キャッシュ管理モジュール
API取得したユーザー情報（ID/氏名/メールアドレス）をメモリキャッシュする
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class UserCacheManager:
    """
    ユーザー情報キャッシュマネージャー（シングルトン）
    
    キャッシュ構造:
    {
        "user_id": {
            "id": "...",
            "userName": "...",
            "emailAddress": "...",
            "familyName": "...",
            "givenName": "...",
            "organizationName": "...",
            "source": "api" | "subgroup_json" | "manual"
        }
    }
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
            cls._instance._initialized = False
        return cls._instance
    
    @classmethod
    def instance(cls):
        """シングルトンインスタンス取得"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        """
        キャッシュからユーザー情報取得
        
        Args:
            user_id: ユーザーID
            
        Returns:
            ユーザー情報辞書、存在しない場合はNone
        """
        return self._cache.get(user_id)
    
    def set_user(self, user_id: str, user_info: Dict, source: str = "api"):
        """
        ユーザー情報をキャッシュに保存
        
        Args:
            user_id: ユーザーID
            user_info: ユーザー情報辞書（userName, emailAddress等）
            source: データソース（"api", "subgroup_json", "manual"）
        """
        if not user_id:
            logger.warning("空のuser_idはキャッシュできません")
            return
        
        cache_entry = user_info.copy()
        cache_entry["id"] = user_id
        cache_entry["source"] = source
        
        self._cache[user_id] = cache_entry
        logger.debug(f"ユーザーキャッシュ保存: {user_id} ({cache_entry.get('userName', 'Unknown')})")
    
    def update_from_api_response(self, user_id: str, api_response: Dict):
        """
        API応答からユーザー情報を抽出してキャッシュ
        
        Args:
            user_id: ユーザーID
            api_response: fetch_user_details_by_id等のAPI応答
        """
        if not api_response:
            return
        
        user_info = {
            "userName": api_response.get("userName", ""),
            "emailAddress": api_response.get("emailAddress", ""),
            "familyName": api_response.get("familyName", ""),
            "givenName": api_response.get("givenName", ""),
            "organizationName": api_response.get("organizationName", ""),
            "isDeleted": api_response.get("isDeleted", False)
        }
        
        self.set_user(user_id, user_info, source="api")
    
    def load_from_subgroup_json(self, user_entries):
        """
        subGroup.jsonのユーザーリストからキャッシュを初期化
        
        Args:
            user_entries: SubgroupDataManager.load_user_entries()の戻り値
        """
        if not user_entries or isinstance(user_entries, str):
            return
        
        loaded_count = 0
        for user in user_entries:
            user_id = user.get("id", "")
            if not user_id:
                continue
            
            attr = user.get("attributes", {})
            user_info = {
                "userName": attr.get("userName", ""),
                "emailAddress": attr.get("emailAddress", ""),
                "familyName": attr.get("familyName", ""),
                "givenName": attr.get("givenName", ""),
                "organizationName": attr.get("organizationName", "")
            }
            
            # 既存キャッシュがない場合のみ保存（API情報を優先）
            if user_id not in self._cache:
                self.set_user(user_id, user_info, source="subgroup_json")
                loaded_count += 1
        
        logger.debug(f"subGroup.jsonから{loaded_count}件のユーザー情報をキャッシュに読み込み")
        self._initialized = True
    
    def clear(self):
        """キャッシュをクリア"""
        self._cache.clear()
        self._initialized = False
        logger.debug("ユーザーキャッシュをクリアしました")
    
    def get_cache_stats(self) -> Dict:
        """キャッシュ統計情報を取得"""
        sources = {}
        for user_info in self._cache.values():
            source = user_info.get("source", "unknown")
            sources[source] = sources.get(source, 0) + 1
        
        return {
            "total": len(self._cache),
            "by_source": sources,
            "initialized": self._initialized
        }
    
    def is_initialized(self) -> bool:
        """キャッシュが初期化済みか確認"""
        return self._initialized
    
    def add_subgroup_to_cache(self, subgroup_data: Dict):
        """
        新規サブグループ情報をキャッシュに追加
        
        Args:
            subgroup_data: fetch_subgroup_by_idのAPI応答（新規サブグループ情報）
        """
        if not subgroup_data:
            return
        
        # includedセクションからユーザー情報を抽出してキャッシュに追加
        included = subgroup_data.get("included", [])
        added_count = 0
        
        for item in included:
            if item.get("type") == "user":
                user_id = item.get("id", "")
                if not user_id:
                    continue
                
                attr = item.get("attributes", {})
                user_info = {
                    "userName": attr.get("userName", ""),
                    "emailAddress": attr.get("emailAddress", ""),
                    "familyName": attr.get("familyName", ""),
                    "givenName": attr.get("givenName", ""),
                    "organizationName": attr.get("organizationName", "")
                }
                
                # 既存キャッシュを上書き（新規サブグループのユーザー情報が最新）
                self.set_user(user_id, user_info, source="api")
                added_count += 1
        
        logger.info(f"新規サブグループから{added_count}件のユーザー情報をキャッシュに追加")



# グローバルアクセス用ヘルパー関数
def get_cached_user(user_id: str) -> Optional[Dict]:
    """キャッシュからユーザー情報取得"""
    return UserCacheManager.instance().get_user(user_id)


def cache_user(user_id: str, user_info: Dict, source: str = "api"):
    """ユーザー情報をキャッシュに保存"""
    UserCacheManager.instance().set_user(user_id, user_info, source)


def cache_user_from_api(user_id: str, api_response: Dict):
    """API応答からキャッシュ保存"""
    UserCacheManager.instance().update_from_api_response(user_id, api_response)
