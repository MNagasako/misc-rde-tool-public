"""
一時フォルダ管理とファイル整理機能

フラット化・ZIP化時の一時フォルダ作成とマッピング管理を提供
"""

import os
import shutil
import tempfile
import zipfile
import uuid
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import pandas as pd
from dataclasses import dataclass

from classes.data_entry.core.file_set_manager import FileSet, FileItem, FileType, PathOrganizeMethod


@dataclass
class FileMapping:
    """ファイルマッピング情報"""
    original_path: str          # 元のファイルパス
    temp_path: str              # 一時フォルダ内のパス
    register_name: str          # 登録時のファイル名
    file_type: str              # データファイル/添付ファイル
    size: int                   # ファイルサイズ
    relative_path: str          # 元の相対パス


class TempFolderManager:
    """一時フォルダ管理クラス"""
    
    def __init__(self, base_temp_dir: Optional[str] = None):
        """
        初期化
        
        Args:
            base_temp_dir: 一時フォルダのベースディレクトリ（Noneの場合はシステム標準）
        """
        self.base_temp_dir = base_temp_dir or tempfile.gettempdir()
        self.temp_folders: Dict[int, str] = {}  # file_set_id -> temp_folder_path
        self.file_mappings: Dict[int, List[FileMapping]] = {}  # file_set_id -> mappings
        
    def create_temp_folder_for_fileset(self, file_set: FileSet) -> Tuple[str, str]:
        """
        ファイルセット用の一時フォルダを作成
        
        Args:
            file_set: ファイルセットオブジェクト
            
        Returns:
            tuple: (一時フォルダパス, マッピングExcelファイルパス)
        """
        try:
            # 一時フォルダ作成
            temp_dir = tempfile.mkdtemp(
                prefix=f"rde_batch_{file_set.id}_{uuid.uuid4().hex[:8]}_",
                dir=self.base_temp_dir
            )
            
            self.temp_folders[file_set.id] = temp_dir
            
            # ファイル整理処理
            if file_set.organize_method == PathOrganizeMethod.FLATTEN:
                mapping_xlsx = self._create_flatten_structure(file_set, temp_dir)
            elif file_set.organize_method == PathOrganizeMethod.ZIP:
                mapping_xlsx = self._create_zip_structure(file_set, temp_dir)
            else:
                raise ValueError(f"サポートされていない整理方法: {file_set.organize_method}")
            
            print(f"[INFO] ファイルセット {file_set.id} の一時フォルダを作成: {temp_dir}")
            return temp_dir, mapping_xlsx
            
        except Exception as e:
            print(f"[ERROR] 一時フォルダ作成エラー: {e}")
            raise
    
    def _create_flatten_structure(self, file_set: FileSet, temp_dir: str) -> str:
        """
        フラット化構造で一時フォルダを作成
        
        Args:
            file_set: ファイルセットオブジェクト
            temp_dir: 一時フォルダパス
            
        Returns:
            str: マッピングExcelファイルのパス
        """
        mappings = []
        file_name_counter = {}  # 重複ファイル名のカウンタ
        
        valid_items = file_set.get_valid_items()
        file_items = [item for item in valid_items if item.file_type == FileType.FILE]
        
        for file_item in file_items:
            if not os.path.exists(file_item.path):
                print(f"[WARNING] ファイルが存在しません: {file_item.path}")
                continue
            
            # 相対パスを基準にしたフラット化ファイル名を決定
            # ディレクトリの区切り文字を__(ダブルアンダースコア)に置き換える
            relative_path = file_item.relative_path.replace('/', '__').replace('\\', '__')
            
            # フラット化後のファイル名
            flatten_name = relative_path
            
            # 同名ファイルの重複対策
            original_flatten_name = flatten_name
            counter = 1
            while any(m.register_name == flatten_name for m in mappings):
                # 拡張子を分離して番号を挿入
                name_parts = original_flatten_name.rsplit('.', 1)
                if len(name_parts) == 2:
                    flatten_name = f"{name_parts[0]}_{counter}.{name_parts[1]}"
                else:
                    flatten_name = f"{original_flatten_name}_{counter}"
                counter += 1
            
            # ファイルをコピー
            temp_file_path = os.path.join(temp_dir, flatten_name)
            shutil.copy2(file_item.path, temp_file_path)
            
            # マッピング情報を記録
            mapping = FileMapping(
                original_path=file_item.path,
                temp_path=temp_file_path,
                register_name=flatten_name,
                file_type=self._get_file_category(file_item),
                size=file_item.size,
                relative_path=file_item.relative_path
            )
            mappings.append(mapping)
        
        self.file_mappings[file_set.id] = mappings
        
        # マッピングExcelファイルを作成
        mapping_xlsx = self._create_mapping_excel(file_set, mappings, temp_dir)
        
        return mapping_xlsx
    
    def _create_zip_structure(self, file_set: FileSet, temp_dir: str) -> str:
        """
        ZIP化構造で一時フォルダを作成
        
        Args:
            file_set: ファイルセットオブジェクト
            temp_dir: 一時フォルダパス
            
        Returns:
            str: マッピングExcelファイルのパス
        """
        mappings = []
        
        # ディレクトリごとにZIPファイルを作成
        valid_items = file_set.get_valid_items()
        
        # ルートレベルのファイルとディレクトリを分離
        root_files = []
        directories = {}
        
        for item in valid_items:
            relative_path = Path(item.relative_path)
            
            if len(relative_path.parts) == 1:
                # ルートレベルのアイテム
                if item.file_type == FileType.FILE:
                    root_files.append(item)
            else:
                # ディレクトリ配下のアイテム
                dir_name = relative_path.parts[0]
                if dir_name not in directories:
                    directories[dir_name] = []
                if item.file_type == FileType.FILE:
                    directories[dir_name].append(item)
        
        # ルートレベルのファイルを直接コピー
        for file_item in root_files:
            if not os.path.exists(file_item.path):
                continue
                
            temp_file_path = os.path.join(temp_dir, file_item.name)
            shutil.copy2(file_item.path, temp_file_path)
            
            mapping = FileMapping(
                original_path=file_item.path,
                temp_path=temp_file_path,
                register_name=file_item.name,
                file_type=self._get_file_category(file_item),
                size=file_item.size,
                relative_path=file_item.relative_path
            )
            mappings.append(mapping)
        
        # ディレクトリごとにZIPファイルを作成
        for dir_name, files in directories.items():
            if not files:
                continue
                
            zip_file_path = os.path.join(temp_dir, f"{dir_name}.zip")
            
            with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_item in files:
                    if not os.path.exists(file_item.path):
                        continue
                    
                    # ZIP内での相対パス
                    relative_path = Path(file_item.relative_path)
                    zip_internal_path = '/'.join(relative_path.parts[1:])  # ディレクトリ名を除く
                    
                    zipf.write(file_item.path, zip_internal_path)
            
            # ZIPファイル全体のマッピング情報を記録
            zip_size = os.path.getsize(zip_file_path)
            mapping = FileMapping(
                original_path=f"ディレクトリ: {dir_name} ({len(files)}ファイル)",
                temp_path=zip_file_path,
                register_name=f"{dir_name}.zip",
                file_type="データファイル",  # ZIPファイルはデータファイルとして扱う
                size=zip_size,
                relative_path=dir_name
            )
            mappings.append(mapping)
        
        self.file_mappings[file_set.id] = mappings
        
        # マッピングExcelファイルを作成
        mapping_xlsx = self._create_mapping_excel(file_set, mappings, temp_dir)
        
        return mapping_xlsx
    
    def _create_mapping_excel(self, file_set: FileSet, mappings: List[FileMapping], temp_dir: str) -> str:
        """
        ファイルマッピング情報のExcelファイルを作成
        
        Args:
            file_set: ファイルセットオブジェクト
            mappings: マッピング情報リスト
            temp_dir: 一時フォルダパス
            
        Returns:
            str: 作成されたExcelファイルのパス
        """
        # DataFrameを作成
        data = []
        for mapping in mappings:
            data.append({
                '元ファイルパス': mapping.original_path,
                '元相対パス': mapping.relative_path,
                '登録ファイル名': mapping.register_name,
                'ファイル種別': mapping.file_type,
                'ファイルサイズ': mapping.size,
                'サイズ(MB)': round(mapping.size / 1024 / 1024, 3),
                '一時ファイルパス': mapping.temp_path
            })
        
        df = pd.DataFrame(data)
        
        # Excelファイルを作成
        xlsx_filename = "path_map.xlsx"
        xlsx_path = os.path.join(temp_dir, xlsx_filename)
        
        with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
            # マッピング情報シート
            df.to_excel(writer, sheet_name='ファイルマッピング', index=False)
            
            # サマリー情報シート
            summary_data = {
                'ファイルセット名': [file_set.name],
                '整理方法': [file_set.organize_method.value],
                'ベースディレクトリ': [file_set.base_directory],
                'ファイル数': [len(mappings)],
                '総サイズ(MB)': [round(sum(m.size for m in mappings) / 1024 / 1024, 3)],
                '作成日時': [pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='サマリー', index=False)
        
        print(f"[INFO] マッピングExcelファイルを作成: {xlsx_path}")
        
        # ファイル作成確認
        if os.path.exists(xlsx_path):
            print(f"[INFO] マッピングファイル作成確認: {xlsx_path}")
        else:
            print(f"[WARNING] マッピングファイル作成失敗: {xlsx_path}")
        
        return xlsx_path
    
    def _get_file_category(self, file_item: FileItem) -> str:
        """ファイルカテゴリを取得"""
        # プレビューで設定された値を優先
        if hasattr(file_item, '_file_category') and file_item._file_category:
            return file_item._file_category
        
        # データファイルとして扱う拡張子
        data_extensions = {
            '.csv', '.xlsx', '.xls', '.txt', '.dat', '.json', '.xml',
            '.h5', '.hdf5', '.nc', '.cdf', '.mat', '.npz', '.npy'
        }
        
        try:
            if file_item.extension and file_item.extension.lower() in data_extensions:
                return "データファイル"
            else:
                return "添付ファイル"
        except:
            return "添付ファイル"
    
    def get_temp_folder(self, file_set_id: int) -> Optional[str]:
        """ファイルセットIDから一時フォルダパスを取得"""
        return self.temp_folders.get(file_set_id)
    
    def get_file_mappings(self, file_set_id: int) -> List[FileMapping]:
        """ファイルセットIDからファイルマッピング情報を取得"""
        return self.file_mappings.get(file_set_id, [])
    
    def cleanup_temp_folder(self, file_set_id: int) -> bool:
        """指定ファイルセットの一時フォルダを削除"""
        try:
            temp_dir = self.temp_folders.get(file_set_id)
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                print(f"[INFO] 一時フォルダを削除: {temp_dir}")
                
            # 管理データをクリア
            if file_set_id in self.temp_folders:
                del self.temp_folders[file_set_id]
            if file_set_id in self.file_mappings:
                del self.file_mappings[file_set_id]
                
            return True
        except Exception as e:
            print(f"[ERROR] 一時フォルダ削除エラー: {e}")
            return False
    
    def cleanup_all_temp_folders(self):
        """全ての一時フォルダを削除"""
        for file_set_id in list(self.temp_folders.keys()):
            self.cleanup_temp_folder(file_set_id)
    
    def __del__(self):
        """デストラクタで一時フォルダをクリーンアップ"""
        try:
            self.cleanup_all_temp_folders()
        except:
            pass
