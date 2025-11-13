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

import logging

# ロガー設定
logger = logging.getLogger(__name__)

from classes.data_entry.core.file_set_manager import FileSet, FileItem, FileType, PathOrganizeMethod, FileItemType


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
    """一時フォルダ管理クラス（UUID対応版）"""
    
    def __init__(self, base_temp_dir: Optional[str] = None):
        """
        初期化
        
        Args:
            base_temp_dir: 一時フォルダのベースディレクトリ（Noneの場合はoutput/temp）
        """
        if base_temp_dir is None:
            from config.common import get_output_directory
            self.base_temp_dir = os.path.join(get_output_directory(), "temp")
        else:
            self.base_temp_dir = base_temp_dir
        
        # ベースディレクトリが存在することを確認
        if not os.path.exists(self.base_temp_dir):
            os.makedirs(self.base_temp_dir, exist_ok=True)
            logger.info("一時フォルダベースディレクトリを作成: %s", self.base_temp_dir)
        
        # 後方互換性のため残しておく（UUID管理に移行中）
        self.temp_folders: Dict[int, str] = {}  # file_set_id -> temp_folder_path
        self.file_mappings: Dict[int, List[FileMapping]] = {}  # file_set_id -> mappings
        
    def get_stable_temp_folder_path(self, file_set: FileSet) -> str:
        """ファイルセットUUIDに基づく安定的な一時フォルダパスを取得"""
        folder_name = f"fileset_{file_set.uuid}"
        return os.path.join(self.base_temp_dir, folder_name)
    
    def get_stable_mapping_file_path(self, file_set: FileSet) -> str:
        """ファイルセットUUIDに基づく安定的なマッピングファイルパスを取得"""
        temp_folder = self.get_stable_temp_folder_path(file_set)
        return os.path.join(temp_folder, "path_mapping.xlsx")
    
    def create_temp_folder_for_fileset(self, file_set: FileSet) -> Tuple[str, str]:
        """
        ファイルセット用の一時フォルダを作成（UUID固定版）
        
        Args:
            file_set: ファイルセットオブジェクト
            
        Returns:
            tuple: (一時フォルダパス, マッピングExcelファイルパス)
        """
        try:
            # UUIDベースの固定パスを取得
            temp_dir = self.get_stable_temp_folder_path(file_set)
            
            # 既存フォルダをクリーンアップして再作成
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.info("既存の一時フォルダをクリーンアップ: %s", temp_dir)
            
            os.makedirs(temp_dir, exist_ok=True)
            logger.info("一時フォルダを作成: %s", temp_dir)
            
            # ファイルセットに固定パスを設定
            file_set.temp_folder_path = temp_dir
            file_set.mapping_file_path = self.get_stable_mapping_file_path(file_set)
            
            # 後方互換性のためIDベースの管理も更新
            self.temp_folders[file_set.id] = temp_dir
            
            # ファイル整理処理
            if file_set.organize_method == PathOrganizeMethod.FLATTEN:
                mapping_xlsx = self._create_flatten_structure(file_set, temp_dir)
            elif file_set.organize_method == PathOrganizeMethod.ZIP:
                mapping_xlsx = self._create_zip_structure(file_set, temp_dir)
            else:
                raise ValueError(f"サポートされていない整理方法: {file_set.organize_method}")
            
            # ファイルセットのマッピングファイルパスを更新
            file_set.mapping_file_path = mapping_xlsx
            
            logger.info("ファイルセット %s (UUID: %s) の一時フォルダを作成: %s", file_set.name, file_set.uuid, temp_dir)
            return temp_dir, mapping_xlsx
            
        except Exception as e:
            logger.error("一時フォルダ作成エラー: %s", e)
            raise
    
    def _create_flatten_structure(self, file_set: FileSet, temp_dir: str) -> str:
        """
        フラット化構造で一時フォルダを作成（ZIP化考慮版）
        
        Args:
            file_set: ファイルセットオブジェクト
            temp_dir: 一時フォルダパス
            
        Returns:
            str: マッピングExcelファイルのパス
        """
        mappings = []
        file_name_counter = {}  # 重複ファイル名のカウンタ
        
        valid_items = file_set.get_valid_items()
        
        # ZIP化対象となるディレクトリを特定
        zip_directories = set()
        for item in valid_items:
            if item.file_type == FileType.DIRECTORY and hasattr(item, 'is_zip') and item.is_zip:
                zip_directories.add(item.relative_path)
                logger.debug("フラット化でもZIP化対象ディレクトリ: %s", item.relative_path)
        
        # ZIP化対象ディレクトリを処理
        for zip_dir in zip_directories:
            # このディレクトリ配下のファイルを収集
            zip_files = []
            for item in valid_items:
                if (item.file_type == FileType.FILE and 
                    (item.relative_path.startswith(zip_dir + '/') or item.relative_path.startswith(zip_dir + '\\'))):
                    zip_files.append(item)
            
            if zip_files:
                # ZIPファイルを作成
                zip_filename = f"{Path(zip_dir).name}.zip"
                zip_file_path = os.path.join(temp_dir, zip_filename)
                
                with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_item in zip_files:
                        if not os.path.exists(file_item.path):
                            continue
                        
                        # ZIP内での相対パス（ディレクトリ構造を保持）
                        zip_internal_path = file_item.relative_path
                        if zip_internal_path.startswith(zip_dir):
                            # ディレクトリプレフィックスを削除
                            zip_internal_path = zip_internal_path[len(zip_dir):].lstrip('/\\')
                        
                        zipf.write(file_item.path, zip_internal_path)
                        logger.debug("フラット化ZIP内に追加: %s -> %s", file_item.path, zip_internal_path)
                
                # ZIPファイルのマッピング情報を記録
                zip_size = os.path.getsize(zip_file_path)
                mapping = FileMapping(
                    original_path=f"ディレクトリ: {zip_dir} ({len(zip_files)}ファイル)",
                    temp_path=zip_file_path,
                    register_name=zip_filename,
                    file_type="データファイル",
                    size=zip_size,
                    relative_path=zip_dir
                )
                mappings.append(mapping)
                logger.info("フラット化でZIP化完了: %s (%sファイル)", zip_file_path, len(zip_files))
        
        # 通常のファイル（ZIP化対象外）を処理
        for file_item in [item for item in valid_items if item.file_type == FileType.FILE]:
            # ZIP化対象ディレクトリ配下のファイルはスキップ
            is_in_zip_dir = False
            for zip_dir in zip_directories:
                if (file_item.relative_path.startswith(zip_dir + '/') or 
                    file_item.relative_path.startswith(zip_dir + '\\')):
                    is_in_zip_dir = True
                    break
            
            if is_in_zip_dir:
                continue  # ZIP化済みなのでスキップ
            
            if not os.path.exists(file_item.path):
                logger.warning("ファイルが存在しません: %s", file_item.path)
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
        
        valid_items = file_set.get_valid_items()
        
        # ZIP化対象となるディレクトリを特定
        zip_directories = set()
        for item in valid_items:
            if item.file_type == FileType.DIRECTORY and getattr(item, 'is_zip', False):
                zip_directories.add(item.relative_path)
                logger.debug("ZIP化対象ディレクトリ: %s (is_zip=%s)", item.relative_path, item.is_zip)
        
        logger.debug("ZIP化対象ディレクトリ総数: %s", len(zip_directories))
        for zip_dir in zip_directories:
            logger.debug("- %s", zip_dir)
        # ディレクトリごとにファイルを整理（ZIP化を考慮）
        root_files = []
        directories = {}
        files_to_skip = set()  # ZIP化対象ディレクトリ配下のファイルをスキップするため
        
        for item in valid_items:
            if item.file_type != FileType.FILE:
                continue
                
            relative_path = Path(item.relative_path)
            
            # このファイルがZIP化対象ディレクトリ配下かチェック
            is_in_zip_dir = False
            zip_dir_name = None
            for zip_dir in zip_directories:
                if item.relative_path.startswith(zip_dir + '/') or item.relative_path.startswith(zip_dir + '\\'):
                    is_in_zip_dir = True
                    zip_dir_name = zip_dir
                    break
            
            if is_in_zip_dir:
                # ZIP化対象ディレクトリ配下のファイルは個別コピーしない
                files_to_skip.add(item.path)
                if zip_dir_name not in directories:
                    directories[zip_dir_name] = []
                directories[zip_dir_name].append(item)
            elif len(relative_path.parts) == 1:
                # ルートレベルのファイル
                root_files.append(item)
            else:
                # 通常のディレクトリ配下のファイル（ZIP化対象外）
                dir_name = relative_path.parts[0]
                if dir_name not in directories:
                    directories[dir_name] = []
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
        
        # ディレクトリごとに処理
        for dir_name, files in directories.items():
            if not files:
                continue
                
            # このディレクトリがZIP化対象かチェック
            should_zip = dir_name in zip_directories
            
            if should_zip:
                # ZIPファイルとして作成
                zip_file_path = os.path.join(temp_dir, f"{Path(dir_name).name}.zip")
                logger.debug("ZIP作成開始: %s", zip_file_path)
                logger.debug("ZIP対象ファイル数: %s", len(files))
                
                with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_item in files:
                        if not os.path.exists(file_item.path):
                            logger.warning("ファイルが存在しません: %s", file_item.path)
                            continue
                        
                        # ZIP内での相対パス（ディレクトリ構造を保持）
                        zip_internal_path = file_item.relative_path
                        if zip_internal_path.startswith(dir_name):
                            # ディレクトリプレフィックスを削除
                            zip_internal_path = zip_internal_path[len(dir_name):].lstrip('/\\')
                        
                        logger.debug("ZIP内に追加:")
                        logger.debug("元ファイル: %s", file_item.path)
                        logger.debug("相対パス: %s", file_item.relative_path)
                        logger.debug("ZIP内パス: %s", zip_internal_path)
                        
                        zipf.write(file_item.path, zip_internal_path)
                
                # ZIPファイル全体のマッピング情報を記録
                zip_size = os.path.getsize(zip_file_path)
                logger.debug("ZIP作成完了: %s (%s bytes)", zip_file_path, zip_size)
                
                mapping = FileMapping(
                    original_path=f"ディレクトリ: {dir_name} ({len(files)}ファイル)",
                    temp_path=zip_file_path,
                    register_name=f"{Path(dir_name).name}.zip",
                    file_type="添付ファイル",  # ZIP化されたファイルは添付ファイル
                    size=zip_size,
                    relative_path=dir_name
                )
                mappings.append(mapping)
                logger.info("ZIP化完了: %s (%sファイル)", zip_file_path, len(files))
            else:
                # 通常のファイルコピー
                for file_item in files:
                    if not os.path.exists(file_item.path):
                        continue
                        
                    # ファイル名の重複を避けるためにディレクトリプレフィックスを付ける
                    safe_filename = file_item.relative_path.replace('/', '_').replace('\\', '_')
                    temp_file_path = os.path.join(temp_dir, safe_filename)
                    shutil.copy2(file_item.path, temp_file_path)
                    
                    mapping = FileMapping(
                        original_path=file_item.path,
                        temp_path=temp_file_path,
                        register_name=safe_filename,
                        file_type=self._get_file_category(file_item),
                        size=file_item.size,
                        relative_path=file_item.relative_path
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
        # DataFrameを作成（絶対パス列・一時ファイルパス列を除外、英語カラム名に変更）
        data = []
        for mapping in mappings:
            data.append({
                'original_path': mapping.relative_path,  # 元相対パス
                'flattened_name': mapping.register_name, # 登録ファイル名
                'file_type': mapping.file_type,          # ファイル種別
                'file_size': mapping.size,               # ファイルサイズ
                'size_mb': round(mapping.size / 1024 / 1024, 3) # サイズ(MB)
            })
        df = pd.DataFrame(data)
        # Excelファイルを作成 (固定ファイル名を使用)
        xlsx_filename = "path_mapping.xlsx"
        xlsx_path = os.path.join(temp_dir, xlsx_filename)
        with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
            # filemapシートのみ出力
            df.to_excel(writer, sheet_name='filemap', index=False)
        logger.info("マッピングExcelファイルを作成: %s", xlsx_path)
        # ファイル作成確認
        if os.path.exists(xlsx_path):
            logger.info("マッピングファイル作成確認: %s", xlsx_path)
        else:
            logger.warning("マッピングファイル作成失敗: %s", xlsx_path)
        
        return xlsx_path
    
    def _get_file_category(self, file_item: FileItem) -> str:
        """ファイルカテゴリを取得"""
        # FileItemTypeを使用して種類を決定
        if file_item.item_type == FileItemType.ATTACHMENT:
            return "添付ファイル"
        else:
            return "データファイル"
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
                logger.info("一時フォルダを削除: %s", temp_dir)
                
            # 管理データをクリア
            if file_set_id in self.temp_folders:
                del self.temp_folders[file_set_id]
            if file_set_id in self.file_mappings:
                del self.file_mappings[file_set_id]
                
            return True
        except Exception as e:
            logger.error("一時フォルダ削除エラー: %s", e)
            return False
    
    def cleanup_temp_folder_by_uuid(self, fileset_uuid: str) -> bool:
        """ファイルセットUUIDに基づいて一時フォルダを削除"""
        try:
            folder_name = f"fileset_{fileset_uuid}"
            temp_dir = os.path.join(self.base_temp_dir, folder_name)
            
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.info("UUID %s の一時フォルダを削除: %s", fileset_uuid, temp_dir)
                return True
            else:
                logger.info("UUID %s の一時フォルダは存在しません: %s", fileset_uuid, temp_dir)
                return False
                
        except Exception as e:
            logger.error("UUID %s の一時フォルダ削除エラー: %s", fileset_uuid, e)
            return False
    
    def cleanup_all_temp_folders(self):
        """全ての一時フォルダを削除"""
        try:
            if os.path.exists(self.base_temp_dir):
                for item in os.listdir(self.base_temp_dir):
                    item_path = os.path.join(self.base_temp_dir, item)
                    if os.path.isdir(item_path) and item.startswith('fileset_'):
                        shutil.rmtree(item_path)
                        logger.info("一時フォルダを削除: %s", item_path)
            
            # 後方互換性用の管理データもクリア
            self.temp_folders.clear()
            self.file_mappings.clear()
            
        except Exception as e:
            logger.error("全一時フォルダ削除エラー: %s", e)
    
    def get_orphaned_temp_folders(self, active_filesets: List[FileSet]) -> List[str]:
        """孤立した一時フォルダを検索"""
        orphaned = []
        
        try:
            if not os.path.exists(self.base_temp_dir):
                return orphaned
            
            # アクティブなUUID一覧を作成
            active_uuids = {fs.uuid for fs in active_filesets}
            
            # 一時フォルダ内を検索
            for item in os.listdir(self.base_temp_dir):
                item_path = os.path.join(self.base_temp_dir, item)
                if os.path.isdir(item_path) and item.startswith('fileset_'):
                    uuid_part = item[8:]  # 'fileset_' を除去
                    if uuid_part not in active_uuids:
                        orphaned.append(item_path)
        
        except Exception as e:
            logger.error("孤立フォルダ検索エラー: %s", e)
        
        return orphaned
    
    def cleanup_orphaned_temp_folders(self, active_filesets: List[FileSet]) -> int:
        """孤立した一時フォルダを削除"""
        orphaned = self.get_orphaned_temp_folders(active_filesets)
        cleaned_count = 0
        
        for folder_path in orphaned:
            try:
                shutil.rmtree(folder_path)
                logger.info("孤立した一時フォルダを削除: %s", folder_path)
                cleaned_count += 1
            except Exception as e:
                logger.error("孤立フォルダ削除エラー (%s): %s", folder_path, e)
        
        return cleaned_count
    
    def __del__(self):
        """デストラクタで一時フォルダをクリーンアップ"""
        try:
            # 新しい管理方式では自動クリーンアップは行わない（手動管理）
            pass
        except:
            pass
