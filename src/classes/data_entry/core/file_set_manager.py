"""
一括登録用ファイルセットクラス

ファイルセット: 一括登録において一つの単位として処理されるファイル・ディレクトリの集合
"""

import os
import json
import uuid
import datetime
from typing import List, Dict, Optional, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class PathOrganizeMethod(Enum):
    """パス整理方法の列挙"""
    ZIP = "zip"              # ZIP化
    FLATTEN = "flatten"      # フラット化


class FileType(Enum):
    """ファイルタイプの列挙"""
    FILE = "file"
    DIRECTORY = "directory"


class FileItemType(Enum):
    """ファイルアイテムの種別（データファイル/添付ファイル）"""
    DATA = "data"            # データファイル
    ATTACHMENT = "attachment" # 添付ファイル


@dataclass
class FileItem:
    """ファイル・ディレクトリの情報を表現するクラス"""
    path: str                           # 絶対パス
    relative_path: str                  # ベースディレクトリからの相対パス
    name: str                          # ファイル・ディレクトリ名
    file_type: FileType                # ファイル or ディレクトリ
    extension: str = ""                # 拡張子（ファイルの場合）
    size: int = 0                      # ファイルサイズ（bytes）
    child_count: int = 0               # 配下ファイル数（ディレクトリの場合）
    is_excluded: bool = False          # 除外フラグ
    item_type: FileItemType = FileItemType.DATA  # ファイル種別（データファイル/添付ファイル）
    is_zip: bool = False               # ZIP化指定フラグ（ディレクトリの場合）
    
    def __post_init__(self):
        """初期化後の処理"""
        if self.file_type == FileType.FILE:
            self.extension = Path(self.name).suffix.lower()
            if os.path.exists(self.path):
                self.size = os.path.getsize(self.path)
        elif self.file_type == FileType.DIRECTORY:
            if os.path.exists(self.path):
                self.child_count = self._count_files_recursive()
    
    def _count_files_recursive(self) -> int:
        """ディレクトリ配下のファイル数を再帰的にカウント"""
        count = 0
        try:
            for root, dirs, files in os.walk(self.path):
                count += len(files)
        except (PermissionError, OSError):
            pass
        return count


@dataclass
class FileSet:
    """一括登録の単位となるファイルセット"""
    id: int                            # ファイルセットID
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))  # ファイルセット固有UUID
    name: str = ""                     # ファイルセット名
    base_directory: str = ""           # ベースディレクトリ
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat())  # 作成日時
    items: List[FileItem] = field(default_factory=list)  # 含まれるファイル・ディレクトリ
    organize_method: PathOrganizeMethod = PathOrganizeMethod.FLATTEN  # パス整理方法
    
    # 一時フォルダ管理情報
    temp_folder_path: Optional[str] = None        # 固定一時フォルダパス
    mapping_file_path: Optional[str] = None       # 固定マッピングファイルパス
    
    # データエントリー情報
    dataset_id: Optional[str] = None                    # データセットID
    dataset_info: Optional[Dict] = None                 # データセット情報
    
    # 共通情報
    data_name: str = ""                # データ名
    description: str = ""              # データ説明
    experiment_id: str = ""            # 実験ID
    reference_url: str = ""            # 参考URL
    tags: str = ""                     # タグ
    
    # 試料情報
    sample_mode: str = "new"           # new/existing/same_as_previous
    sample_id: Optional[str] = None    # 既存試料ID（existing時）
    sample_name: str = ""              # 試料名
    sample_description: str = ""       # 試料説明
    sample_composition: str = ""       # 化学式・組成式・分子式
    
    # 固有情報（インボイススキーマ）
    custom_values: Dict = field(default_factory=dict)  # カスタム値
    
    # 拡張設定（UIフォームからの設定値）
    extended_config: Dict = field(default_factory=dict)  # 拡張設定値
    
    def get_valid_items(self) -> List[FileItem]:
        """除外されていない有効なアイテムを取得"""
        return [item for item in self.items if not item.is_excluded]
    
    def get_total_size(self) -> int:
        """ファイルセットの総サイズを取得（bytes）"""
        return sum(item.size for item in self.get_valid_items() if item.file_type == FileType.FILE)
    
    def get_file_count(self) -> int:
        """ファイルセット内の実際のファイル数を取得（重複カウント回避）"""
        # ファイルアイテムのみをカウント（ディレクトリは除外）
        file_count = 0
        for item in self.get_valid_items():
            if item.file_type == FileType.FILE:
                file_count += 1
        return file_count
    
    def get_directory_count(self) -> int:
        """ファイルセット内のディレクトリ数を取得"""
        directory_count = 0
        for item in self.get_valid_items():
            if item.file_type == FileType.DIRECTORY:
                directory_count += 1
        return directory_count


class FileSetManager:
    """ファイルセットの管理クラス"""
    
    def __init__(self, base_directory: str):
        self.base_directory = os.path.abspath(base_directory)
        self.file_sets: List[FileSet] = []
        self.file_tree: List[FileItem] = []
        self._next_id = 1
        
        # メタデータファイルの管理
        self.metadata_dir = self._get_metadata_directory()
        self._ensure_metadata_directory()
    
    def _get_metadata_directory(self) -> str:
        """メタデータディレクトリのパスを取得"""
        from config.common import get_output_directory
        return os.path.join(get_output_directory(), "filesets_metadata")
    
    def _ensure_metadata_directory(self):
        """メタデータディレクトリが存在することを確認（なければ作成）"""
        if not os.path.exists(self.metadata_dir):
            os.makedirs(self.metadata_dir, exist_ok=True)
            print(f"[INFO] ファイルセットメタデータディレクトリを作成: {self.metadata_dir}")
    
    def save_fileset_metadata(self, file_set: FileSet):
        """ファイルセットのメタデータをJSONファイルに保存"""
        try:
            metadata = {
                'id': file_set.id,
                'uuid': file_set.uuid,
                'name': file_set.name,
                'created_at': file_set.created_at,
                'base_directory': file_set.base_directory,
                'organize_method': file_set.organize_method.value,
                'temp_folder_path': file_set.temp_folder_path,
                'mapping_file_path': file_set.mapping_file_path,
                'dataset_id': file_set.dataset_id,
                'data_name': file_set.data_name,
                'sample_mode': file_set.sample_mode,
                'sample_id': file_set.sample_id,
                'sample_name': file_set.sample_name,
                'file_count': file_set.get_file_count(),
                'total_size': file_set.get_total_size(),
                'items_count': len(file_set.items)
            }
            
            # UUIDベースのファイル名でメタデータを保存
            metadata_file = os.path.join(self.metadata_dir, f"{file_set.uuid}.json")
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            print(f"[INFO] ファイルセットメタデータを保存: {metadata_file}")
            
        except Exception as e:
            print(f"[ERROR] メタデータ保存エラー: {e}")
    
    def load_fileset_metadata(self, fileset_uuid: str) -> Optional[Dict]:
        """UUIDからファイルセットのメタデータを読み込み"""
        try:
            metadata_file = os.path.join(self.metadata_dir, f"{fileset_uuid}.json")
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                return metadata
            return None
        except Exception as e:
            print(f"[ERROR] メタデータ読み込みエラー: {e}")
            return None
    
    def cleanup_fileset_metadata(self, fileset_uuid: str):
        """ファイルセットのメタデータファイルを削除"""
        try:
            metadata_file = os.path.join(self.metadata_dir, f"{fileset_uuid}.json")
            if os.path.exists(metadata_file):
                os.remove(metadata_file)
                print(f"[INFO] ファイルセットメタデータを削除: {metadata_file}")
        except Exception as e:
            print(f"[ERROR] メタデータ削除エラー: {e}")
    
    def get_all_fileset_metadata(self) -> List[Dict]:
        """全ファイルセットのメタデータ一覧を取得"""
        metadata_list = []
        try:
            if os.path.exists(self.metadata_dir):
                for filename in os.listdir(self.metadata_dir):
                    if filename.endswith('.json'):
                        uuid_str = filename[:-5]  # .json拡張子を除去
                        metadata = self.load_fileset_metadata(uuid_str)
                        if metadata:
                            metadata_list.append(metadata)
            
            # 作成日時でソート
            metadata_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
        except Exception as e:
            print(f"[ERROR] 全メタデータ取得エラー: {e}")
        
        return metadata_list
    
    def build_file_tree(self) -> List[FileItem]:
        """ベースディレクトリからファイルツリーを構築"""
        self.file_tree = []
        
        if not os.path.exists(self.base_directory):
            raise FileNotFoundError(f"ベースディレクトリが存在しません: {self.base_directory}")
        
        for root, dirs, files in os.walk(self.base_directory):
            # ディレクトリを追加
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                relative_path = os.path.relpath(dir_path, self.base_directory)
                
                file_item = FileItem(
                    path=dir_path,
                    relative_path=relative_path,
                    name=dir_name,
                    file_type=FileType.DIRECTORY
                )
                self.file_tree.append(file_item)
            
            # ファイルを追加
            for file_name in files:
                file_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(file_path, self.base_directory)
                
                file_item = FileItem(
                    path=file_path,
                    relative_path=relative_path,
                    name=file_name,
                    file_type=FileType.FILE
                )
                self.file_tree.append(file_item)
        
        # パスでソート
        self.file_tree.sort(key=lambda x: x.relative_path)
        return self.file_tree
    
    def auto_assign_filesets_all_as_one(self) -> List[FileSet]:
        """自動割り当て: 全体で一つのファイルセット（フラット化）"""
        self.file_sets = []
        
        if not self.file_tree:
            return self.file_sets
        
        file_set = FileSet(
            id=self._next_id,
            name="全体ファイルセット",
            base_directory=self.base_directory,
            items=self.file_tree.copy(),
            organize_method=PathOrganizeMethod.FLATTEN
        )
        
        self.file_sets.append(file_set)
        self._next_id += 1
        
        # メタデータを保存
        self.save_fileset_metadata(file_set)
        
        return self.file_sets
    
    def auto_assign_filesets_by_top_level_dirs(self) -> List[FileSet]:
        """自動割り当て: 最も浅い階層のフォルダごとにファイルセット（排他制御付き）"""
        self.file_sets = []
        
        if not self.file_tree:
            return self.file_sets
        
        # 割り当て済みのアイテムを追跡（排他制御）
        assigned_items = set()
        
        # 最も浅い階層のディレクトリを取得
        top_level_dirs = set()
        root_files = []
        
        for item in self.file_tree:
            path_parts = item.relative_path.split(os.sep)
            if len(path_parts) == 1:
                if item.file_type == FileType.DIRECTORY:
                    top_level_dirs.add(item.relative_path)
                else:
                    root_files.append(item)
        
        # 各トップレベルディレクトリをファイルセットに（排他制御）
        for top_dir in sorted(top_level_dirs):
            items = []
            for item in self.file_tree:
                # 既に他のファイルセットに割り当て済みでないか確認
                if item.relative_path not in assigned_items:
                    # 指定フォルダ内のアイテムか確認
                    if item.relative_path.startswith(top_dir + os.sep) or item.relative_path == top_dir:
                        # 上位フォルダが含まれていないかチェック
                        item_parts = item.relative_path.split(os.sep)
                        is_descendant = (len(item_parts) >= len(top_dir.split(os.sep)) and
                                       item.relative_path.startswith(top_dir))
                        
                        if is_descendant:
                            items.append(item)
                            assigned_items.add(item.relative_path)
            
            if items:
                file_set = FileSet(
                    id=self._next_id,
                    name=f"フォルダ: {top_dir}",
                    base_directory=self.base_directory,
                    items=items,
                    organize_method=PathOrganizeMethod.FLATTEN
                )
                self.file_sets.append(file_set)
                self._next_id += 1
                
                # メタデータを保存
                self.save_fileset_metadata(file_set)
        
        # ルートファイルがある場合は別ファイルセットに（未割り当てのみ）
        unassigned_root_files = [f for f in root_files if f.relative_path not in assigned_items]
        if unassigned_root_files:
            file_set = FileSet(
                id=self._next_id,
                name="ルートファイル",
                base_directory=self.base_directory,
                items=unassigned_root_files,
                organize_method=PathOrganizeMethod.FLATTEN
            )
            self.file_sets.append(file_set)
            self._next_id += 1
            
            # メタデータを保存
            self.save_fileset_metadata(file_set)
            
            # ルートファイルも割り当て済みに追加
            for item in unassigned_root_files:
                assigned_items.add(item.relative_path)
        
        return self.file_sets
    
    def auto_assign_filesets_all_directories(self) -> List[FileSet]:
        """自動割り当て: 全てのフォルダを個別ファイルセット（排他制御付き）"""
        self.file_sets = []
        
        if not self.file_tree:
            return self.file_sets
        
        # 割り当て済みのアイテムを追跡（排他制御）
        assigned_items = set()
        
        # ディレクトリごとにファイルセットを作成（階層が深い順にソート）
        directories = [item for item in self.file_tree if item.file_type == FileType.DIRECTORY]
        # 深い階層から処理することで、下位フォルダが上位フォルダより先に処理される
        directories.sort(key=lambda x: x.relative_path.count(os.sep), reverse=True)
        
        for dir_item in directories:
            # 既に他のファイルセットに割り当て済みでないか確認
            if dir_item.relative_path in assigned_items:
                continue
                
            items = [dir_item]  # ディレクトリ自体を含む
            assigned_items.add(dir_item.relative_path)
            
            # 配下のファイル・ディレクトリを追加（未割り当てのもののみ）
            for item in self.file_tree:
                if item.relative_path not in assigned_items:
                    # 指定ディレクトリの下位かチェック
                    if (item.relative_path.startswith(dir_item.relative_path + os.sep) and 
                        item.relative_path != dir_item.relative_path):
                        # 上位フォルダが含まれていないか確認
                        is_direct_descendant = True
                        item_parent_path = os.path.dirname(item.relative_path)
                        
                        # 間に他のディレクトリがないか確認
                        while item_parent_path and item_parent_path != dir_item.relative_path:
                            if item_parent_path in assigned_items:
                                is_direct_descendant = False
                                break
                            item_parent_path = os.path.dirname(item_parent_path)
                        
                        if is_direct_descendant:
                            items.append(item)
                            assigned_items.add(item.relative_path)
            
            if len(items) > 1 or (len(items) == 1 and items[0].file_type == FileType.DIRECTORY):
                file_set = FileSet(
                    id=self._next_id,
                    name=f"ディレクトリ: {dir_item.name}",
                    base_directory=self.base_directory,
                    items=items,
                    organize_method=PathOrganizeMethod.FLATTEN
                )
                self.file_sets.append(file_set)
                self._next_id += 1
        
        # ルートファイルがある場合は別ファイルセットに（未割り当てのみ）
        root_files = [item for item in self.file_tree 
                      if (item.file_type == FileType.FILE and 
                          os.sep not in item.relative_path and
                          item.relative_path not in assigned_items)]
        
        if root_files:
            file_set = FileSet(
                id=self._next_id,
                name="ルートファイル",
                base_directory=self.base_directory,
                items=root_files,
                organize_method=PathOrganizeMethod.FLATTEN
            )
            self.file_sets.append(file_set)
            self._next_id += 1
        
        return self.file_sets
    
    def create_manual_fileset(self, name: str, selected_items: List[FileItem], 
                             organize_method: PathOrganizeMethod = PathOrganizeMethod.FLATTEN) -> FileSet:
        """手動でファイルセットを作成（階層制御付き）"""
        # 選択されたアイテムを正規化（フォルダ選択時の階層制御）
        normalized_items = self._normalize_manual_selection(selected_items)
        
        file_set = FileSet(
            id=self._next_id,
            name=name,
            base_directory=self.base_directory,
            items=normalized_items,
            organize_method=organize_method
        )
        
        self.file_sets.append(file_set)
        self._next_id += 1
        
        # メタデータを保存
        self.save_fileset_metadata(file_set)
        
        return file_set
    
    def _normalize_manual_selection(self, selected_items: List[FileItem]) -> List[FileItem]:
        """手動選択の正規化（階層制御）"""
        normalized = []
        selected_paths = {item.relative_path for item in selected_items}
        
        for item in selected_items:
            if item.file_type == FileType.DIRECTORY:
                # フォルダが選択された場合
                # 1. 上位フォルダを除外
                has_parent_in_selection = False
                for other_item in selected_items:
                    if (other_item.file_type == FileType.DIRECTORY and 
                        other_item.relative_path != item.relative_path and
                        item.relative_path.startswith(other_item.relative_path + os.sep)):
                        has_parent_in_selection = True
                        break
                
                if not has_parent_in_selection:
                    # 2. 下位のファイル・フォルダを全て含める
                    normalized.append(item)
                    for file_item in self.file_tree:
                        if (file_item.relative_path.startswith(item.relative_path + os.sep) and
                            file_item.relative_path not in selected_paths):
                            normalized.append(file_item)
            else:
                # ファイルが選択された場合
                # 上位フォルダが選択されていなければ含める
                has_parent_folder_in_selection = False
                for other_item in selected_items:
                    if (other_item.file_type == FileType.DIRECTORY and
                        item.relative_path.startswith(other_item.relative_path + os.sep)):
                        has_parent_folder_in_selection = True
                        break
                
                if not has_parent_folder_in_selection:
                    normalized.append(item)
        
        return normalized
    
    def remove_fileset(self, fileset_id: int) -> bool:
        """ファイルセットを削除（関連データも削除）"""
        for i, file_set in enumerate(self.file_sets):
            if file_set.id == fileset_id:
                # メタデータを削除
                self.cleanup_fileset_metadata(file_set.uuid)
                
                # 一時フォルダも削除
                if file_set.temp_folder_path and os.path.exists(file_set.temp_folder_path):
                    try:
                        import shutil
                        shutil.rmtree(file_set.temp_folder_path)
                        print(f"[INFO] ファイルセット削除時に一時フォルダを削除: {file_set.temp_folder_path}")
                    except Exception as e:
                        print(f"[WARNING] 一時フォルダ削除失敗: {e}")
                
                # ファイルセットを削除
                del self.file_sets[i]
                return True
        return False
    
    def clear_all_filesets(self):
        """全ファイルセットを削除（関連データも削除）"""
        print(f"[DEBUG] clear_all_filesets: {len(self.file_sets)}個のファイルセットを削除")
        
        # 全ファイルセットを削除（逆順で安全に削除）
        for file_set in reversed(self.file_sets[:]):
            # メタデータを削除
            self.cleanup_fileset_metadata(file_set.uuid)
            
            # 一時フォルダも削除
            if hasattr(file_set, 'temp_folder_path') and file_set.temp_folder_path and os.path.exists(file_set.temp_folder_path):
                try:
                    import shutil
                    shutil.rmtree(file_set.temp_folder_path)
                    print(f"[INFO] 全削除時に一時フォルダを削除: {file_set.temp_folder_path}")
                except Exception as e:
                    print(f"[WARNING] 一時フォルダ削除失敗: {e}")
        
        # リストをクリア
        self.file_sets.clear()
        print(f"[DEBUG] clear_all_filesets: 削除完了")
    
    def get_fileset_by_id(self, fileset_id: int) -> Optional[FileSet]:
        """IDでファイルセットを取得"""
        for file_set in self.file_sets:
            if file_set.id == fileset_id:
                return file_set
        return None
    
    def validate_filesets(self) -> Tuple[bool, List[str]]:
        """ファイルセットの妥当性を検証"""
        errors = []
        
        # 各ファイルセットに有効なアイテムが含まれているかチェック
        for file_set in self.file_sets:
            valid_items = file_set.get_valid_items()
            if not valid_items:
                errors.append(f"ファイルセット '{file_set.name}' に有効なファイルが含まれていません")
        
        # ファイルが複数のファイルセットに含まれていないかチェック
        all_paths = set()
        for file_set in self.file_sets:
            for item in file_set.get_valid_items():
                if item.path in all_paths:
                    errors.append(f"ファイル '{item.relative_path}' が複数のファイルセットに含まれています")
                else:
                    all_paths.add(item.path)
        
        return len(errors) == 0, errors
    
    def to_dict(self) -> Dict:
        """ファイルセット管理情報を辞書に変換"""
        return {
            "base_directory": self.base_directory,
            "file_tree": [
                {
                    "path": item.path,
                    "relative_path": item.relative_path,
                    "name": item.name,
                    "file_type": item.file_type.value,
                    "extension": item.extension,
                    "size": item.size,
                    "child_count": item.child_count,
                    "is_excluded": item.is_excluded
                }
                for item in self.file_tree
            ],
            "file_sets": [
                {
                    "id": fs.id,
                    "name": fs.name,
                    "base_directory": fs.base_directory,
                    "organize_method": fs.organize_method.value,
                    "dataset_id": fs.dataset_id,
                    "dataset_info": fs.dataset_info,
                    # 共通情報
                    "data_name": fs.data_name,
                    "description": fs.description,
                    "experiment_id": fs.experiment_id,
                    "reference_url": fs.reference_url,
                    "tags": fs.tags,
                    # 試料情報
                    "sample_mode": fs.sample_mode,
                    "sample_id": fs.sample_id,
                    "sample_name": fs.sample_name,
                    "sample_description": fs.sample_description,
                    "sample_composition": fs.sample_composition,
                    # 固有情報
                    "custom_values": fs.custom_values,
                    # アイテム
                    "items": [
                        {
                            "path": item.path,
                            "relative_path": item.relative_path,
                            "name": item.name,
                            "file_type": item.file_type.value,
                            "extension": item.extension,
                            "size": item.size,
                            "child_count": item.child_count,
                            "is_excluded": item.is_excluded
                        }
                        for item in fs.items
                    ]
                }
                for fs in self.file_sets
            ]
        }
    
    def save_to_file(self, file_path: str):
        """ファイルセット管理情報をJSONファイルに保存"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load_from_file(cls, file_path: str) -> 'FileSetManager':
        """JSONファイルからファイルセット管理情報を読み込み"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        manager = cls(data['base_directory'])
        
        # ファイルツリーを復元
        for item_data in data['file_tree']:
            item = FileItem(
                path=item_data['path'],
                relative_path=item_data['relative_path'],
                name=item_data['name'],
                file_type=FileType(item_data['file_type']),
                extension=item_data['extension'],
                size=item_data['size'],
                child_count=item_data['child_count'],
                is_excluded=item_data['is_excluded']
            )
            manager.file_tree.append(item)
        
        # ファイルセットを復元
        for fs_data in data['file_sets']:
            # アイテムを復元
            items = []
            for item_data in fs_data['items']:
                item = FileItem(
                    path=item_data['path'],
                    relative_path=item_data['relative_path'],
                    name=item_data['name'],
                    file_type=FileType(item_data['file_type']),
                    extension=item_data['extension'],
                    size=item_data['size'],
                    child_count=item_data['child_count'],
                    is_excluded=item_data['is_excluded']
                )
                items.append(item)
            
            # ファイルセットを復元
            file_set = FileSet(
                id=fs_data['id'],
                name=fs_data['name'],
                base_directory=fs_data['base_directory'],
                organize_method=PathOrganizeMethod(fs_data['organize_method']),
                items=items,
                dataset_id=fs_data.get('dataset_id'),
                dataset_info=fs_data.get('dataset_info'),
                data_name=fs_data.get('data_name', ''),
                description=fs_data.get('description', ''),
                experiment_id=fs_data.get('experiment_id', ''),
                reference_url=fs_data.get('reference_url', ''),
                tags=fs_data.get('tags', ''),
                sample_mode=fs_data.get('sample_mode', 'new'),
                sample_id=fs_data.get('sample_id'),
                sample_name=fs_data.get('sample_name', ''),
                sample_description=fs_data.get('sample_description', ''),
                sample_composition=fs_data.get('sample_composition', ''),
                custom_values=fs_data.get('custom_values', {})
            )
            manager.file_sets.append(file_set)
            manager._next_id = max(manager._next_id, file_set.id + 1)
        
        return manager
