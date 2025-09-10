"""
一括登録用ファイルセットクラス

ファイルセット: 一括登録において一つの単位として処理されるファイル・ディレクトリの集合
"""

import os
import json
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
    name: str                          # ファイルセット名
    base_directory: str                # ベースディレクトリ
    items: List[FileItem] = field(default_factory=list)  # 含まれるファイル・ディレクトリ
    organize_method: PathOrganizeMethod = PathOrganizeMethod.FLATTEN  # パス整理方法
    
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


class FileSetManager:
    """ファイルセットの管理クラス"""
    
    def __init__(self, base_directory: str):
        self.base_directory = os.path.abspath(base_directory)
        self.file_sets: List[FileSet] = []
        self.file_tree: List[FileItem] = []
        self._next_id = 1
    
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
        """ファイルセットを削除"""
        for i, file_set in enumerate(self.file_sets):
            if file_set.id == fileset_id:
                del self.file_sets[i]
                return True
        return False
    
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
