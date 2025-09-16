"""
一括登録メインロジッククラス

ファイルセット群から一括でデータエントリー登録を実行する
"""

import os
import json
import zipfile
import shutil
import tempfile
from typing import List, Dict, Optional, Tuple, Callable
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal, QThread
from PyQt5.QtWidgets import QApplication, QProgressDialog, QMessageBox

from .file_set_manager import FileSet, FileSetManager, FileItem, FileType, PathOrganizeMethod
from .data_register_logic_wrapper import DataRegisterLogic


class BatchRegisterResult:
    """一括登録結果クラス"""
    
    def __init__(self):
        self.total_filesets = 0
        self.success_count = 0
        self.error_count = 0
        self.errors: List[Tuple[str, str]] = []  # (ファイルセット名, エラーメッセージ)
        self.success_filesets: List[str] = []    # 成功したファイルセット名
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """成功率を取得"""
        if self.total_filesets == 0:
            return 0.0
        return (self.success_count / self.total_filesets) * 100
    
    @property
    def duration(self) -> Optional[float]:
        """処理時間を取得（秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    def to_dict(self) -> Dict:
        """結果を辞書に変換"""
        return {
            "total_filesets": self.total_filesets,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": self.success_rate,
            "duration": self.duration,
            "errors": self.errors,
            "success_filesets": self.success_filesets,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None
        }


class BatchRegisterWorker(QThread):
    """一括登録ワーカースレッド"""
    
    # シグナル定義
    progress_updated = pyqtSignal(int, str)  # (進捗%, メッセージ)
    fileset_started = pyqtSignal(str)        # ファイルセット開始
    fileset_completed = pyqtSignal(str)      # ファイルセット完了
    fileset_error = pyqtSignal(str, str)     # (ファイルセット名, エラーメッセージ)
    finished = pyqtSignal(object)            # BatchRegisterResult
    
    def __init__(self, file_sets: List[FileSet], temp_base_dir: str):
        super().__init__()
        self.file_sets = file_sets
        self.temp_base_dir = temp_base_dir
        self.result = BatchRegisterResult()
        self._cancelled = False
    
    def cancel(self):
        """処理をキャンセル"""
        self._cancelled = True
    
    def run(self):
        """メイン処理"""
        self.result.start_time = datetime.now()
        self.result.total_filesets = len(self.file_sets)
        
        try:
            for i, file_set in enumerate(self.file_sets):
                if self._cancelled:
                    break
                
                # 進捗更新
                progress = int((i / len(self.file_sets)) * 100)
                self.progress_updated.emit(progress, f"処理中: {file_set.name}")
                self.fileset_started.emit(file_set.name)
                
                try:
                    # ファイルセット登録処理
                    self._register_fileset(file_set)
                    
                    self.result.success_count += 1
                    self.result.success_filesets.append(file_set.name)
                    self.fileset_completed.emit(file_set.name)
                    
                except Exception as e:
                    error_msg = str(e)
                    self.result.error_count += 1
                    self.result.errors.append((file_set.name, error_msg))
                    self.fileset_error.emit(file_set.name, error_msg)
            
            # 完了
            self.progress_updated.emit(100, "一括登録完了")
            
        except Exception as e:
            self.result.errors.append(("システムエラー", str(e)))
        
        finally:
            self.result.end_time = datetime.now()
            self.finished.emit(self.result)
    
    def _register_fileset(self, file_set: FileSet):
        """個別ファイルセットの登録処理"""
        # ベアラートークンを取得（グローバルから）
        from ..ui.batch_preview_dialog import FileSetPreviewWidget
        from core.bearer_token_helper import get_current_bearer_token
        # Bearerトークンを共通ヘルパーで取得（通常登録タブ方式に統一）
        bearer_token = get_current_bearer_token()
        if not bearer_token:
            raise Exception("認証トークンが設定されていません。ログインを確認してください。")
        # データセット情報の確認
        if not file_set.dataset_id:
            raise Exception("データセットIDが設定されていません。")
        # ファイルセット情報をdataset_infoの形式に変換
        dataset_info = {
            'id': file_set.dataset_id,
            'relationships': {},
            'attributes': {}
        }
        # プレビューウィジェット作成（一時的）
        preview_widget = FileSetPreviewWidget(file_set, bearer_token=bearer_token)
        
        try:
            # フォーム値構築
            form_values = preview_widget._build_form_values_from_fileset()
            
            # アップロード処理実行
            upload_success = preview_widget._execute_batch_upload()
            if not upload_success:
                raise Exception("ファイルアップロードに失敗しました。")
            
            # データ登録処理実行
            registration_success = preview_widget._execute_data_registration()
            if not registration_success:
                raise Exception("データ登録に失敗しました。")
                
        except Exception as e:
            raise Exception(f"ファイルセット '{file_set.name}' の登録処理でエラーが発生: {str(e)}")
        
        finally:
            # プレビューウィジェットをクリーンアップ
            if preview_widget:
                preview_widget.deleteLater()
    
    def _organize_files(self, file_set: FileSet, temp_dir: str) -> List[str]:
        """ファイル整理処理"""
        valid_items = file_set.get_valid_items()
        organized_files = []
        
        if file_set.organize_method == PathOrganizeMethod.FLATTEN:
            # フラット化
            organized_files = self._flatten_files(valid_items, temp_dir)
        elif file_set.organize_method == PathOrganizeMethod.ZIP:
            # ZIP化
            organized_files = self._zip_files(file_set, valid_items, temp_dir)
        
        return organized_files
    
    def _flatten_files(self, items: List[FileItem], temp_dir: str) -> List[str]:
        """フラット化処理"""
        organized_files = []
        file_counter = {}  # 重複ファイル名対応
        
        for item in items:
            if item.file_type == FileType.FILE:
                # ファイルをフラットにコピー
                base_name = Path(item.name).stem
                extension = Path(item.name).suffix
                
                # 重複ファイル名の処理
                if item.name in file_counter:
                    file_counter[item.name] += 1
                    new_name = f"{base_name}_{file_counter[item.name]}{extension}"
                else:
                    file_counter[item.name] = 0
                    new_name = item.name
                
                dest_path = os.path.join(temp_dir, new_name)
                shutil.copy2(item.path, dest_path)
                organized_files.append(dest_path)
            
            elif item.file_type == FileType.DIRECTORY:
                # ディレクトリ内のファイルを再帰的にフラット化
                for root, dirs, files in os.walk(item.path):
                    for file_name in files:
                        file_path = os.path.join(root, file_name)
                        
                        # ファイル名重複対応
                        base_name = Path(file_name).stem
                        extension = Path(file_name).suffix
                        
                        if file_name in file_counter:
                            file_counter[file_name] += 1
                            new_name = f"{base_name}_{file_counter[file_name]}{extension}"
                        else:
                            file_counter[file_name] = 0
                            new_name = file_name
                        
                        dest_path = os.path.join(temp_dir, new_name)
                        shutil.copy2(file_path, dest_path)
                        organized_files.append(dest_path)
        
        return organized_files
    
    def _zip_files(self, file_set: FileSet, items: List[FileItem], temp_dir: str) -> List[str]:
        """ZIP化処理"""
        zip_path = os.path.join(temp_dir, f"{file_set.name}.zip")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for item in items:
                if item.file_type == FileType.FILE:
                    # ファイルをZIPに追加
                    zipf.write(item.path, item.relative_path)
                
                elif item.file_type == FileType.DIRECTORY:
                    # ディレクトリを再帰的にZIPに追加
                    for root, dirs, files in os.walk(item.path):
                        for file_name in files:
                            file_path = os.path.join(root, file_name)
                            # ベースディレクトリからの相対パスを計算
                            relative_path = os.path.relpath(file_path, file_set.base_directory)
                            zipf.write(file_path, relative_path)
        
        return [zip_path]


class BatchRegisterLogic(QObject):
    """一括登録メインロジッククラス"""
    
    # シグナル定義
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal(object)  # BatchRegisterResult
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.progress_dialog = None
        self.temp_base_dir = None
    
    def run_batch_register(self, file_sets: List[FileSet], 
                          show_progress: bool = True) -> BatchRegisterResult:
        """一括登録実行"""
        if not file_sets:
            result = BatchRegisterResult()
            result.errors.append(("入力エラー", "登録するファイルセットがありません"))
            return result
        
        # 一時ディレクトリ作成
        self.temp_base_dir = tempfile.mkdtemp(prefix="batch_register_")
        
        try:
            # ワーカースレッド作成
            self.worker = BatchRegisterWorker(file_sets, self.temp_base_dir)
            
            # シグナル接続
            self.worker.progress_updated.connect(self.progress_updated)
            self.worker.finished.connect(self._on_worker_finished)
            
            # プログレスダイアログ表示
            if show_progress:
                self._show_progress_dialog(len(file_sets))
            
            # 処理開始
            self.worker.start()
            
            # 処理完了まで待機
            self.worker.wait()
            
            return self.worker.result
            
        except Exception as e:
            result = BatchRegisterResult()
            result.errors.append(("システムエラー", str(e)))
            return result
        
        finally:
            # 一時ディレクトリクリーンアップ
            if self.temp_base_dir and os.path.exists(self.temp_base_dir):
                shutil.rmtree(self.temp_base_dir, ignore_errors=True)
    
    def _show_progress_dialog(self, total_filesets: int):
        """プログレスダイアログ表示"""
        self.progress_dialog = QProgressDialog(
            "一括登録を実行中...", "キャンセル", 0, 100
        )
        self.progress_dialog.setWindowTitle("一括登録")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()
        
        # キャンセルボタン処理
        def on_cancel():
            if self.worker:
                self.worker.cancel()
        
        self.progress_dialog.canceled.connect(on_cancel)
        
        # 進捗更新処理
        def on_progress_updated(progress, message):
            if self.progress_dialog:
                self.progress_dialog.setValue(progress)
                self.progress_dialog.setLabelText(message)
                QApplication.processEvents()
        
        self.progress_updated.connect(on_progress_updated)
    
    def _on_worker_finished(self, result: BatchRegisterResult):
        """ワーカー完了処理"""
        # プログレスダイアログ閉じる
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        
        # 結果をシグナルで通知
        self.finished.emit(result)
    
    def validate_filesets(self, file_sets: List[FileSet]) -> Tuple[bool, List[str]]:
        """ファイルセット群の妥当性検証"""
        errors = []
        
        if not file_sets:
            errors.append("登録するファイルセットがありません")
            return False, errors
        
        # 各ファイルセットの検証
        for file_set in file_sets:
            # 有効なファイルがあるかチェック
            valid_items = file_set.get_valid_items()
            if not valid_items:
                errors.append(f"ファイルセット '{file_set.name}' に有効なファイルが含まれていません")
            
            # データセットIDチェック
            if not file_set.dataset_id:
                errors.append(f"ファイルセット '{file_set.name}' にデータセットIDが設定されていません")
            
            # データ名チェック
            if not file_set.data_name and not file_set.name:
                errors.append(f"ファイルセット '{file_set.name}' にデータ名が設定されていません")
            
            # 試料情報チェック
            if file_set.sample_mode == "existing" and not file_set.sample_id:
                errors.append(f"ファイルセット '{file_set.name}' で既存試料モードが選択されていますが、試料IDが設定されていません")
        
        return len(errors) == 0, errors
    
    def preview_batch_register(self, file_sets: List[FileSet]) -> Dict:
        """一括登録プレビュー"""
        preview = {
            "total_filesets": len(file_sets),
            "total_files": 0,
            "total_size": 0,
            "filesets": []
        }
        
        for file_set in file_sets:
            valid_items = file_set.get_valid_items()
            file_count = file_set.get_file_count()
            total_size = file_set.get_total_size()
            
            fileset_preview = {
                "name": file_set.name,
                "file_count": file_count,
                "total_size": total_size,
                "organize_method": file_set.organize_method.value,
                "dataset_id": file_set.dataset_id,
                "data_name": file_set.data_name or file_set.name,
                "sample_mode": file_set.sample_mode,
                "valid_items": len(valid_items)
            }
            
            preview["filesets"].append(fileset_preview)
            preview["total_files"] += file_count
            preview["total_size"] += total_size
        
        return preview
    
    def export_batch_result(self, result: BatchRegisterResult, file_path: str):
        """一括登録結果をファイルにエクスポート"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)


def format_file_size(size_bytes: int) -> str:
    """ファイルサイズを人間が読みやすい形式に変換"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"


def estimate_processing_time(file_count: int, total_size: int) -> str:
    """処理時間を推定"""
    # 簡易推定：ファイル数 * 2秒 + サイズ(MB) * 0.1秒
    estimated_seconds = file_count * 2 + (total_size / (1024 * 1024)) * 0.1
    
    if estimated_seconds < 60:
        return f"約 {int(estimated_seconds)} 秒"
    elif estimated_seconds < 3600:
        minutes = int(estimated_seconds / 60)
        return f"約 {minutes} 分"
    else:
        hours = int(estimated_seconds / 3600)
        minutes = int((estimated_seconds % 3600) / 60)
        return f"約 {hours} 時間 {minutes} 分"
