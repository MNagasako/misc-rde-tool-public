import logging

# ロガー設定
logger = logging.getLogger(__name__)

"""
データセット・サブグループ更新通知システム
"""

class DatasetRefreshNotifier:
    """データセット更新を他のウィジェットに通知するためのクラス"""
    
    def __init__(self):
        self.callbacks = []
    
    def register_callback(self, callback):
        """リフレッシュコールバックを登録"""
        if callback not in self.callbacks:
            self.callbacks.append(callback)
            logger.info("データセットリフレッシュコールバック登録: %s件", len(self.callbacks))
    
    def unregister_callback(self, callback):
        """リフレッシュコールバックを登録解除"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
            logger.info("データセットリフレッシュコールバック解除: %s件", len(self.callbacks))
    
    def notify_refresh(self):
        """全ての登録されたコールバックに更新を通知"""
        logger.info("データセット更新を%s件のコールバックに通知", len(self.callbacks))
        for callback in self.callbacks:
            try:
                callback()
            except Exception as e:
                logger.error("データセットリフレッシュコールバック実行エラー: %s", e)


class SubgroupRefreshNotifier:
    """サブグループ更新を他のウィジェットに通知するためのクラス"""
    
    def __init__(self):
        self.callbacks = []
    
    def register_callback(self, callback):
        """リフレッシュコールバックを登録"""
        if callback not in self.callbacks:
            self.callbacks.append(callback)
            logger.info("サブグループリフレッシュコールバック登録: %s件", len(self.callbacks))
    
    def unregister_callback(self, callback):
        """リフレッシュコールバックを登録解除"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
            logger.info("サブグループリフレッシュコールバック解除: %s件", len(self.callbacks))
    
    def notify_refresh(self):
        """全ての登録されたコールバックに更新を通知"""
        logger.info("サブグループ更新を%s件のコールバックに通知", len(self.callbacks))
        for callback in self.callbacks:
            try:
                callback()
            except Exception as e:
                logger.error("サブグループリフレッシュコールバック実行エラー: %s", e)


# グローバルインスタンス
_global_dataset_notifier = DatasetRefreshNotifier()
_global_subgroup_notifier = SubgroupRefreshNotifier()

def get_dataset_refresh_notifier():
    """グローバルデータセット通知インスタンスを取得"""
    return _global_dataset_notifier

def get_subgroup_refresh_notifier():
    """グローバルサブグループ通知インスタンスを取得"""
    return _global_subgroup_notifier
