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
            print(f"[INFO] データセットリフレッシュコールバック登録: {len(self.callbacks)}件")
    
    def unregister_callback(self, callback):
        """リフレッシュコールバックを登録解除"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
            print(f"[INFO] データセットリフレッシュコールバック解除: {len(self.callbacks)}件")
    
    def notify_refresh(self):
        """全ての登録されたコールバックに更新を通知"""
        print(f"[INFO] データセット更新を{len(self.callbacks)}件のコールバックに通知")
        for callback in self.callbacks:
            try:
                callback()
            except Exception as e:
                print(f"[ERROR] データセットリフレッシュコールバック実行エラー: {e}")


class SubgroupRefreshNotifier:
    """サブグループ更新を他のウィジェットに通知するためのクラス"""
    
    def __init__(self):
        self.callbacks = []
    
    def register_callback(self, callback):
        """リフレッシュコールバックを登録"""
        if callback not in self.callbacks:
            self.callbacks.append(callback)
            print(f"[INFO] サブグループリフレッシュコールバック登録: {len(self.callbacks)}件")
    
    def unregister_callback(self, callback):
        """リフレッシュコールバックを登録解除"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
            print(f"[INFO] サブグループリフレッシュコールバック解除: {len(self.callbacks)}件")
    
    def notify_refresh(self):
        """全ての登録されたコールバックに更新を通知"""
        print(f"[INFO] サブグループ更新を{len(self.callbacks)}件のコールバックに通知")
        for callback in self.callbacks:
            try:
                callback()
            except Exception as e:
                print(f"[ERROR] サブグループリフレッシュコールバック実行エラー: {e}")


# グローバルインスタンス
_global_dataset_notifier = DatasetRefreshNotifier()
_global_subgroup_notifier = SubgroupRefreshNotifier()

def get_dataset_refresh_notifier():
    """グローバルデータセット通知インスタンスを取得"""
    return _global_dataset_notifier

def get_subgroup_refresh_notifier():
    """グローバルサブグループ通知インスタンスを取得"""
    return _global_subgroup_notifier
