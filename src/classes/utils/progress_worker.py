"""
プログレス表示用のワーカークラス

長時間処理にプログレス表示を提供する共通クラス
"""
import time
from qt_compat.core import QObject, Signal

class ProgressWorker(QObject):
    """プログレス表示付きの処理を実行するワーカー"""
    progress = Signal(int, str)  # (進捗率, メッセージ)
    # (現在, 総数, メッセージ)
    # show_progress_dialog 側で planned/current/ETA 表示に利用する。
    progress_detail = Signal(int, int, str)
    finished = Signal(bool, str)  # (成功/失敗, 結果メッセージ)
    
    def __init__(self, task_func, task_args=None, task_kwargs=None, task_name="処理"):
        super().__init__()
        self.task_func = task_func
        self.task_args = task_args or []
        self.task_kwargs = task_kwargs or {}
        self.task_name = task_name
        self.is_cancelled = False
        
    def run(self):
        """タスクを実行してプログレスを更新"""
        try:
            self.progress.emit(0, f"{self.task_name}を開始しています...")
            try:
                self.progress_detail.emit(0, 0, f"{self.task_name}を開始しています...")
            except Exception:
                pass
            time.sleep(0.1)  # UI更新のための短時間待機
            
            # プログレスコールバック関数を定義
            def progress_callback(current, total, message="処理中"):
                if self.is_cancelled:
                    return False
                # currentとtotalの型をチェック
                # parallel_download()は(progress_percent, 100, message)形式で呼ぶ
                # 他の関数は(current_count, total_count, message)形式で呼ぶ
                if total == 100 and current <= 100:
                    # 既にパーセント値の場合（parallel_download()から）
                    progress_percent = int(current)
                else:
                    # カウント値の場合
                    if total > 0:
                        # 体感改善: 初期の0%張り付き回避のため、切り上げで進捗率を算出する。
                        # 例: 1/500 -> 1% になる
                        progress_percent = min(int((int(current) * 100 + int(total) - 1) / int(total)), 100)
                    else:
                        progress_percent = 0

                self.progress.emit(progress_percent, message)
                try:
                    self.progress_detail.emit(int(current), int(total), message)
                except Exception:
                    pass
                return True
                
            # task_kwargsにprogress_callbackを追加
            enhanced_kwargs = self.task_kwargs.copy()
            enhanced_kwargs['progress_callback'] = progress_callback
            
            # タスク実行
            result = self.task_func(*self.task_args, **enhanced_kwargs)
            
            if not self.is_cancelled:
                self.progress.emit(100, f"{self.task_name}が完了しました")
                # resultが文字列なら詳細メッセージとして使用、それ以外はデフォルトメッセージ
                if isinstance(result, str) and result:
                    self.finished.emit(True, result)
                else:
                    self.finished.emit(True, f"{self.task_name}が正常に完了しました")
                
        except Exception as e:
            self.progress.emit(100, f"{self.task_name}でエラーが発生しました")
            self.finished.emit(False, f"{self.task_name}でエラー: {str(e)}")
    
    def cancel(self):
        """処理をキャンセル"""
        self.is_cancelled = True


class SimpleProgressWorker(QObject):
    """シンプルなプログレス表示ワーカー（プログレスコールバック不要な処理用）"""
    progress = Signal(int, str)
    finished = Signal(bool, str)
    
    def __init__(self, task_func, task_args=None, task_kwargs=None, task_name="処理"):
        super().__init__()
        self.task_func = task_func
        self.task_args = task_args or []
        self.task_kwargs = task_kwargs or {}
        self.task_name = task_name
        self.is_cancelled = False
        
    def run(self):
        """タスクを実行（シンプル版）"""
        try:
            self.progress.emit(0, f"{self.task_name}を開始しています...")
            time.sleep(0.1)
            
            self.progress.emit(50, f"{self.task_name}を実行中...")
            result = self.task_func(*self.task_args, **self.task_kwargs)
            
            if not self.is_cancelled:
                self.progress.emit(100, f"{self.task_name}が完了しました")
                if isinstance(result, str) and result:
                    self.finished.emit(True, result)
                else:
                    self.finished.emit(True, f"{self.task_name}が正常に完了しました")
                
        except Exception as e:
            self.progress.emit(100, f"{self.task_name}でエラーが発生しました")
            self.finished.emit(False, f"{self.task_name}でエラー: {str(e)}")
    
    def cancel(self):
        """処理をキャンセル"""
        self.is_cancelled = True
