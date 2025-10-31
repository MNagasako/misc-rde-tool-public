"""
一括登録プレビューダイアログ

ファイルセットごとの詳細情報、ファイル一覧、設定情報を表示
"""

import os
import json
import urllib.parse
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path
import logging
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget, 
    QTableWidgetItem, QLabel, QPushButton, QTextEdit, QGroupBox,
    QHeaderView, QScrollArea, QWidget, QSplitter, QMessageBox,
    QDialogButtonBox, QComboBox, QProgressDialog, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QColor

from classes.data_entry.core.file_set_manager import FileSet, FileItem, FileType, PathOrganizeMethod, FileItemType

logger = logging.getLogger(__name__)


class FileSetPreviewWidget(QWidget):
    """ファイルセットプレビューウィジェット"""
    
    def __init__(self, file_set: FileSet, duplicate_files: Set[str] = None, bearer_token: str = None):
        super().__init__()
        self.file_set = file_set
        self.duplicate_files = duplicate_files or set()
        self.bearer_token = bearer_token
        self.setup_ui()
        self.setup_dialog_size()
        self.load_data()
    
    def setup_dialog_size(self):
        """ダイアログサイズを設定（ディスプレイ高さの90%）"""
        try:
            from PyQt5.QtWidgets import QDesktopWidget
            desktop = QDesktopWidget()
            screen_rect = desktop.screenGeometry()
            
            # ディスプレイ高さの90%、幅は適切なサイズに設定
            target_height = int(screen_rect.height() * 0.9)
            target_width = min(int(screen_rect.width() * 0.8), 1200)  # 最大1200px
            
            self.resize(target_width, target_height)
            
            # ダイアログを画面中央に配置
            self.move(
                (screen_rect.width() - target_width) // 2,
                (screen_rect.height() - target_height) // 2
            )
            
            print(f"[DEBUG] プレビューダイアログサイズ設定: {target_width}x{target_height}")
        except Exception as e:
            print(f"[WARNING] ダイアログサイズ設定エラー: {e}")
            self.resize(1000, 700)  # フォールバック
    
    def setup_ui(self):
        """UIセットアップ"""
        layout = QVBoxLayout()
        
        # 上部: 基本情報
        info_group = QGroupBox("ファイルセット情報")
        info_layout = QVBoxLayout()
        
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # 中央: ファイル一覧テーブル
        files_group = QGroupBox("含まれるファイル")
        files_layout = QVBoxLayout()
        
        self.files_table = QTableWidget()
        self.files_table.setColumnCount(7)
        self.files_table.setHorizontalHeaderLabels([
            "相対パス", "登録ファイル名", "サイズ", "拡張子", "種別", "状態", "アップロード"
        ])
        
        # テーブルの設定
        header = self.files_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # 相対パス
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # 登録ファイル名
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # サイズ
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 拡張子
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # 種別
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # 状態
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # アップロード
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # 状態
        
        self.files_table.setAlternatingRowColors(True)
        
        # ファイルテーブルの最低高さを設定（複数行が見えるように）
        self.files_table.setMinimumHeight(300)  # 約10-12行表示
        
        files_layout.addWidget(self.files_table)
        
        files_group.setLayout(files_layout)
        layout.addWidget(files_group, 1)  # 拡張可能
        
        # 下部: 詳細設定情報
        settings_group = QGroupBox("設定情報")
        settings_layout = QVBoxLayout()
        
        self.settings_text = QTextEdit()
        self.settings_text.setMaximumHeight(200)
        self.settings_text.setReadOnly(True)
        settings_layout.addWidget(self.settings_text)
        
        # 一時フォルダ操作ボタン
        temp_folder_layout = QHBoxLayout()
        self.open_temp_folder_button = QPushButton("一時フォルダを開く")
        self.open_temp_folder_button.clicked.connect(self._open_temp_folder)
        self.open_mapping_file_button = QPushButton("マッピングファイルを開く")
        self.open_mapping_file_button.clicked.connect(self._open_mapping_file)
        self.update_mapping_button = QPushButton("マッピング更新")
        self.update_mapping_button.clicked.connect(self._update_mapping_file)
        self.export_folder_button = QPushButton("フォルダ書き出し")
        self.export_folder_button.clicked.connect(self._export_fileset_folder)
        
        temp_folder_layout.addWidget(self.open_temp_folder_button)
        temp_folder_layout.addWidget(self.open_mapping_file_button)
        temp_folder_layout.addWidget(self.update_mapping_button)
        temp_folder_layout.addWidget(self.export_folder_button)
        temp_folder_layout.addStretch()
        
        settings_layout.addLayout(temp_folder_layout)
        
        # 一括処理ボタン
        batch_buttons_layout = QHBoxLayout()
        self.batch_upload_button = QPushButton("ファイル一括アップロード")
        self.batch_upload_button.clicked.connect(self._batch_upload_files)
        self.batch_upload_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        self.batch_register_button = QPushButton("データ登録")
        self.batch_register_button.clicked.connect(self._batch_register_data)
        self.batch_register_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        batch_buttons_layout.addWidget(self.batch_upload_button)
        batch_buttons_layout.addWidget(self.batch_register_button)
        batch_buttons_layout.addStretch()
        
        settings_layout.addLayout(batch_buttons_layout)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        self.setLayout(layout)
    
    def load_data(self):
        """データを読み込み"""
        self._load_file_set_info()
        self._load_files_table()
        self._load_settings_info()
        self._update_temp_folder_buttons()
    
    def _load_file_set_info(self):
        """ファイルセット情報を読み込み"""
        try:
            valid_items = self.file_set.get_valid_items()
            file_count = len([item for item in valid_items if item.file_type == FileType.FILE])
            dir_count = len([item for item in valid_items if item.file_type == FileType.DIRECTORY])
            total_size = self.file_set.get_total_size()
            
            # 一時フォルダ情報を取得
            temp_folder_info = ""
            if hasattr(self.file_set, 'extended_config') and self.file_set.extended_config:
                config = self.file_set.extended_config
                if config.get('temp_created'):
                    temp_folder = config.get('temp_folder', '')
                    mapping_file = config.get('mapping_file', '')
                    temp_folder_info = f"""<br>
<b>一時フォルダ:</b> 作成済み<br>
<b>一時フォルダパス:</b> {temp_folder}<br>
<b>マッピングファイル:</b> {os.path.basename(mapping_file) if mapping_file else '未作成'}"""
            
            info_text = f"""
<b>名前:</b> {self.file_set.name or '未設定'}<br>
<b>ベースディレクトリ:</b> {self.file_set.base_directory or '未設定'}<br>
<b>整理方法:</b> {self._get_organize_method_display()}<br>
<b>ファイル数:</b> {file_count}個<br>
<b>ディレクトリ数:</b> {dir_count}個<br>
<b>総サイズ:</b> {self._format_size(total_size)}<br>
<b>データセット:</b> {self.file_set.dataset_id or '未設定'}{temp_folder_info}
"""
            self.info_label.setText(info_text)
        except Exception as e:
            self.info_label.setText(f"情報読み込みエラー: {str(e)}")
    
    def _load_files_table(self):
        """ファイル一覧テーブルを読み込み（ZIP化対応）"""
        try:
            valid_items = self.file_set.get_valid_items()
            file_items = [item for item in valid_items if item.file_type == FileType.FILE]
            
            # ZIP化されたファイルを処理：ZIPファイルのみ表示、ZIP内ファイルは除外
            display_items = self._get_display_file_items(file_items)
            
            self.files_table.setRowCount(len(display_items))
            
            for row, file_item in enumerate(display_items):
                # 相対パス
                self.files_table.setItem(row, 0, QTableWidgetItem(file_item.relative_path or ""))
                
                # 登録ファイル名（整理方法に応じて）
                register_name = self._get_register_filename(file_item)
                item = QTableWidgetItem(register_name)
                
                # ファイル存在チェック
                file_exists = os.path.exists(file_item.path) if file_item.path else False
                
                # 重複チェック
                if file_item.path in self.duplicate_files:
                    item.setBackground(QColor("#ffcccc"))
                    item.setToolTip("重複ファイル: 他のファイルセットに同じファイルが含まれています")
                elif not file_exists:
                    item.setBackground(QColor("#ffffcc"))
                    item.setToolTip("ファイルが存在しません")
                
                self.files_table.setItem(row, 1, item)
                
                # サイズ
                self.files_table.setItem(row, 2, QTableWidgetItem(self._format_size(file_item.size)))
                
                # 拡張子
                self.files_table.setItem(row, 3, QTableWidgetItem(file_item.extension or ""))
                
                # 種別（データファイル/添付ファイル）をコンボボックスで表示
                file_type_combo = QComboBox()
                
                # ZIP化されたファイルかどうかで選択肢を制限
                is_zipped = self._is_file_zipped(file_item)
                is_original_zip = (file_item.extension and file_item.extension.lower() == '.zip')
                
                if is_zipped and not is_original_zip:
                    # ZIP化されたファイル（元からのZIPファイル以外）：添付ファイルのみ
                    file_type_combo.addItems(["添付ファイル"])
                    file_type_combo.setCurrentIndex(0)
                    file_type_combo.setEnabled(False)  # 変更不可
                    file_item.item_type = FileItemType.ATTACHMENT  # 強制的に添付ファイルに設定
                else:
                    # 元からのZIPファイル、またはZIP化されないファイル：両方選択可能
                    file_type_combo.addItems(["データファイル", "添付ファイル"])
                    
                    # 現在の設定を反映
                    if file_item.item_type == FileItemType.ATTACHMENT:
                        file_type_combo.setCurrentIndex(1)  # 添付ファイル
                    else:
                        file_type_combo.setCurrentIndex(0)  # データファイル
                
                # コンボボックスの変更時にファイルアイテムに記録
                file_type_combo.currentTextChanged.connect(
                    lambda text, item=file_item: self._on_file_type_changed(text, item)
                )
                
                self.files_table.setCellWidget(row, 4, file_type_combo)
                
                # 状態
                if file_item.path in self.duplicate_files:
                    status = "重複"
                    status_item = QTableWidgetItem(status)
                    status_item.setForeground(QColor("#cc0000"))
                elif not file_exists:
                    status = "存在しない"
                    status_item = QTableWidgetItem(status)
                    status_item.setForeground(QColor("#cc6600"))
                else:
                    status = "正常"
                    status_item = QTableWidgetItem(status)
                
                self.files_table.setItem(row, 5, status_item)
                
                # アップロードボタン
                upload_btn = QPushButton("アップロード")
                upload_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #007bff;
                        color: white;
                        border: none;
                        padding: 4px 8px;
                        border-radius: 4px;
                        font-size: 12px;
                    }
                    QPushButton:hover {
                        background-color: #0056b3;
                    }
                    QPushButton:disabled {
                        background-color: #6c757d;
                    }
                """)
                
                # ファイルが存在しない場合はボタンを無効化
                if not file_exists:
                    upload_btn.setEnabled(False)
                    upload_btn.setText("存在なし")
                
                # ボタンクリック時の処理
                upload_btn.clicked.connect(
                    lambda checked, item=file_item: self._upload_file(item)
                )
                
                self.files_table.setCellWidget(row, 6, upload_btn)
                
        except Exception as e:
            print(f"ファイルテーブル読み込み中にエラー: {e}")
            # 空のテーブルを表示
            self.files_table.setRowCount(0)
    
    def _load_settings_info(self):
        """設定情報を読み込み"""
        try:
            # 基本情報の詳細取得（属性の存在チェック付き）
            basic_info = []
            basic_info.append(f"  データ名: {getattr(self.file_set, 'data_name', None) or '未設定'}")
            basic_info.append(f"  説明: {getattr(self.file_set, 'description', None) or '未設定'}")
            basic_info.append(f"  実験ID: {getattr(self.file_set, 'experiment_id', None) or '未設定'}")
            basic_info.append(f"  参考URL: {getattr(self.file_set, 'reference_url', None) or '未設定'}")
            basic_info.append(f"  タグ: {getattr(self.file_set, 'tags', None) or '未設定'}")
            
            # 試料情報の詳細取得
            sample_info = []
            sample_mode = getattr(self.file_set, 'sample_mode', None)
            
            print(f"[DEBUG] _load_settings_info - 試料モード取得: sample_mode={sample_mode}")
            
            # 拡張設定から試料情報を補完
            extended_config = getattr(self.file_set, 'extended_config', {})
            
            # 表示モードを取得
            display_mode = self._get_sample_mode_display()
            sample_info.append(f"  モード: {display_mode}")
            
            # モードに応じた詳細情報を取得
            if sample_mode == 'existing' or extended_config.get('sample_mode') == '既存試料使用' or display_mode == '既存試料使用':
                sample_id = getattr(self.file_set, 'sample_id', None) or extended_config.get('sample_id', None)
                sample_name = getattr(self.file_set, 'sample_name', None) or extended_config.get('sample_name', None)
                sample_description = getattr(self.file_set, 'sample_description', None) or extended_config.get('sample_description', None)
                
                print(f"[DEBUG] _load_settings_info - 既存試料モード: sample_id={sample_id}, sample_name={sample_name}")
                
                sample_info.append(f"  既存試料ID: {sample_id or '未設定'}")
                if sample_name:
                    sample_info.append(f"  試料名: {sample_name}")
                if sample_description:
                    sample_info.append(f"  試料説明: {sample_description}")
            else:
                # 新規作成モード
                sample_name = getattr(self.file_set, 'sample_name', None) or extended_config.get('sample_name', None)
                sample_description = getattr(self.file_set, 'sample_description', None) or extended_config.get('sample_description', None)
                sample_composition = getattr(self.file_set, 'sample_composition', None) or extended_config.get('sample_composition', None)
                
                print(f"[DEBUG] _load_settings_info - 新規作成モード: sample_name={sample_name}, sample_composition={sample_composition}")
                
                sample_info.append(f"  試料名: {sample_name or '未設定'}")
                sample_info.append(f"  試料説明: {sample_description or '未設定'}")
                sample_info.append(f"  組成: {sample_composition or '未設定'}")
            
            # 固有情報の詳細取得
            custom_values = getattr(self.file_set, 'custom_values', {}) or {}
            
            # デバッグ情報を出力
            print(f"[DEBUG] プレビュー - ファイルセット属性custom_values: {custom_values}")
            
            # カスタム値が空の場合でも、拡張設定から取得を試行
            extended_config = getattr(self.file_set, 'extended_config', {})
            print(f"[DEBUG] プレビュー - extended_config全体: {extended_config}")
            
            # 拡張設定内のカスタム値やインボイススキーマ関連の値を抽出
            custom_candidates = {}
            
            # まず、明示的にcustom_valuesキーをチェック（null値も含む）
            if 'custom_values' in extended_config:
                extended_custom = extended_config['custom_values']
                if extended_custom:
                    custom_candidates.update(extended_custom)
                    print(f"[DEBUG] プレビュー - extended_config.custom_values: {extended_custom}")
                
                # その他のカスタムフィールドを探す（基本フィールドと内部データ以外）
                basic_fields = {
                    'description', 'experiment_id', 'reference_url', 'tags', 
                    'sample_mode', 'sample_id', 'sample_name', 'sample_description', 
                    'sample_composition', 'temp_folder', 'mapping_file', 'temp_created',
                    'dataset_id', 'dataset_name', 'custom_values', 'data_name',
                    'selected_dataset'  # 内部データセット情報を除外
                }
                
                for key, value in extended_config.items():
                    # 基本フィールド、内部フィールド、プライベートフィールドを除外
                    if key not in basic_fields and value and not key.startswith('_'):
                        custom_candidates[key] = value
                        print(f"[DEBUG] プレビュー - カスタム値候補: {key} = {value}")
                
                # インボイススキーマの項目も検索（よくある固有情報フィールド名）
                schema_fields = [
                    'electron_gun', 'accelerating_voltage', 'observation_method',
                    'ion_species', 'major_processing_observation_conditions', 'remark'
                ]
                
                for field in schema_fields:
                    if field in extended_config and extended_config[field]:
                        custom_candidates[field] = extended_config[field]
                        print(f"[DEBUG] プレビュー - インボイススキーマ項目: {field} = {extended_config[field]}")
                
                custom_values = custom_candidates
                
                # ファイルセット属性に反映（次回以降の取得を効率化）
                self.file_set.custom_values = custom_values
                print(f"[DEBUG] プレビュー - custom_valuesをファイルセット属性に反映: {len([v for v in custom_values.values() if v and v.strip()])}個の非空値")
            
            custom_info = []
            # 空文字列を含む場合もカスタム情報として表示
            non_empty_values = {k: v for k, v in custom_values.items() if v and v.strip()} if custom_values else {}
            empty_values = {k: v for k, v in custom_values.items() if not v or not v.strip()} if custom_values else {}
            
            if non_empty_values:
                custom_info.append(f"  カスタム値: {len(non_empty_values)}個設定済み")
                for key, value in non_empty_values.items():
                    # 値を適切に表示形式に変換
                    if isinstance(value, dict):
                        value_str = f"{{{len(value)} items}}"
                    elif isinstance(value, list):
                        value_str = f"[{len(value)} items]"
                    else:
                        value_str = str(value)
                        if len(value_str) > 50:  # 長い値は省略
                            value_str = value_str[:47] + "..."
                    custom_info.append(f"    {key}: {value_str}")
                    
            if empty_values:
                custom_info.append(f"  空値: {len(empty_values)}個")
                for key in empty_values.keys():
                    custom_info.append(f"    {key}: (空文字列)")
                    
            if not non_empty_values and not empty_values:
                custom_info.append("  設定項目なし")
            
            # 一時フォルダ情報を取得（UUID固定版を優先）
            temp_folder = getattr(self.file_set, 'temp_folder_path', None)
            mapping_file = getattr(self.file_set, 'mapping_file_path', None)
            
            # 後方互換性：旧形式も確認
            if not temp_folder:
                temp_folder = getattr(self.file_set, 'temp_folder', None)
            if not mapping_file:
                mapping_file = getattr(self.file_set, 'mapping_file', None)
            
            # 拡張設定からも一時フォルダ情報を確認
            extended_config = getattr(self.file_set, 'extended_config', {})
            if not temp_folder and 'temp_folder' in extended_config:
                temp_folder = extended_config['temp_folder']
            if not mapping_file and 'mapping_file' in extended_config:
                mapping_file = extended_config['mapping_file']
            
            temp_info = []
            if temp_folder and os.path.exists(temp_folder):
                temp_info.append(f"  一時フォルダ: {temp_folder}")
                temp_info.append(f"  UUID: {getattr(self.file_set, 'uuid', '未設定')}")
                if mapping_file and os.path.exists(mapping_file):
                    temp_info.append(f"  マッピングファイル: {mapping_file}")
                else:
                    temp_info.append(f"  マッピングファイル: 存在しません")
                temp_info.append(f"  整理方法: {self._get_organize_method_display()}")
            else:
                temp_info.append("  一時フォルダ未作成")
                temp_info.append(f"  UUID: {getattr(self.file_set, 'uuid', '未設定')}")
                temp_info.append(f"  整理方法: {self._get_organize_method_display()}")
            
            # 拡張設定の詳細取得
            extended_config = getattr(self.file_set, 'extended_config', {})
            extended_info = []
            if extended_config:
                extended_info.append(f"  拡張設定: {len(extended_config)}項目設定済み")
                for key, value in extended_config.items():
                    extended_info.append(f"    {key}: {value}")
            else:
                extended_info.append("  設定項目なし")
            
            settings_text = f"""基本情報:
{chr(10).join(basic_info)}

試料情報:
{chr(10).join(sample_info)}

固有情報:
{chr(10).join(custom_info)}

一時フォルダ情報:
{chr(10).join(temp_info)}

拡張設定:
{chr(10).join(extended_info)}
"""
            
            self.settings_text.setPlainText(settings_text)
        except Exception as e:
            error_text = f"設定情報読み込みエラー: {str(e)}\n\nスタックトレース:\n"
            import traceback
            error_text += traceback.format_exc()
            self.settings_text.setPlainText(error_text)
    
    def _get_organize_method_display(self) -> str:
        """整理方法の表示名を取得"""
        try:
            if self.file_set.organize_method == PathOrganizeMethod.FLATTEN:
                return "フラット化"
            elif self.file_set.organize_method == PathOrganizeMethod.ZIP:
                return "ZIP化"
            else:
                return str(self.file_set.organize_method.value)
        except:
            return "未設定"
    
    def _get_display_file_items(self, file_items):
        """表示用ファイル項目の取得（ZIP対応）
        
        Args:
            file_items: FileItem のリスト
            
        Returns:
            表示するファイル項目のリスト
        """
        display_items = []
        zip_files_added = set()  # 既に追加されたZIPファイルを追跡
        zip_directories = set()  # ZIP化対象ディレクトリを特定
        
        # まずZIP化対象ディレクトリを特定
        all_items = self.file_set.get_valid_items()
        for item in all_items:
            if item.file_type == FileType.DIRECTORY and getattr(item, 'is_zip', False):
                zip_directories.add(item.relative_path)
                print(f"[DEBUG] プレビュー: ZIP化ディレクトリ特定 - {item.relative_path}")
        
        print(f"[DEBUG] プレビュー: ZIP化対象ディレクトリ数 = {len(zip_directories)}")
        
        for item in file_items:
            # このファイルがZIP化対象ディレクトリ配下かチェック
            is_in_zip_dir = False
            zip_dir_name = None
            for zip_dir in zip_directories:
                if (item.relative_path.startswith(zip_dir + '/') or 
                    item.relative_path.startswith(zip_dir + '\\') or 
                    item.relative_path == zip_dir):
                    is_in_zip_dir = True
                    zip_dir_name = zip_dir
                    break
            
            if is_in_zip_dir and zip_dir_name:
                # ZIP化対象ディレクトリ配下のファイルの場合、ZIPファイルを表示
                zip_filename = self._get_zip_filename_for_directory(zip_dir_name)
                if zip_filename and zip_filename not in zip_files_added:
                    # ZIPファイル項目を作成
                    zip_item = self._create_zip_file_item_for_directory(zip_dir_name, zip_filename)
                    display_items.append(zip_item)
                    zip_files_added.add(zip_filename)
                    print(f"[DEBUG] プレビュー: ZIPファイル追加 - {zip_filename}")
            else:
                # 通常のファイルはそのまま表示
                display_items.append(item)
                print(f"[DEBUG] プレビュー: 通常ファイル追加 - {item.name}")
        
        # path_mapping.xlsx を添付ファイルとして追加
        mapping_file_path = self._get_mapping_file_path()
        if mapping_file_path and os.path.exists(mapping_file_path):
            mapping_item = FileItem(
                path=mapping_file_path,
                relative_path="path_mapping.xlsx",
                name="path_mapping.xlsx",
                file_type=FileType.FILE,
                item_type=FileItemType.ATTACHMENT  # 添付ファイルとして設定
            )
            display_items.append(mapping_item)
            print(f"[DEBUG] プレビュー: path_mapping.xlsx を表示アイテムに追加 - {mapping_file_path}")
        
        print(f"[DEBUG] プレビュー: 最終表示アイテム数 = {len(display_items)}")
        return display_items
    
    def _get_zip_filename_for_directory(self, dir_relative_path):
        """ディレクトリに対応するZIPファイル名を取得
        
        Args:
            dir_relative_path: ディレクトリの相対パス
            
        Returns:
            ZIPファイル名（tempフォルダ内のパス）
        """
        try:
            # tempフォルダが存在するかチェック
            temp_folder = getattr(self.file_set, 'temp_folder_path', None)
            if not temp_folder:
                extended_config = getattr(self.file_set, 'extended_config', {})
                temp_folder = extended_config.get('temp_folder', None)
            
            if not temp_folder or not os.path.exists(temp_folder):
                print(f"[DEBUG] プレビュー: tempフォルダが存在しない - {temp_folder}")
                return None
                
            # ディレクトリ名からZIPファイル名を生成
            dir_name = os.path.basename(dir_relative_path)
            zip_filename = f"{dir_name}.zip"
            zip_path = os.path.join(temp_folder, zip_filename)
            
            if os.path.exists(zip_path):
                print(f"[DEBUG] プレビュー: ZIPファイル発見 - {zip_path}")
                return zip_path
            else:
                print(f"[DEBUG] プレビュー: ZIPファイル未発見 - {zip_path}")
                
            return None
            
        except Exception as e:
            print(f"[ERROR] プレビュー: ZIP ファイル名取得エラー: {e}")
            return None
    
    def _create_zip_file_item_for_directory(self, dir_relative_path, zip_path):
        """ディレクトリに対応するZIPファイル項目の作成
        
        Args:
            dir_relative_path: ディレクトリの相対パス
            zip_path: ZIPファイルのパス
            
        Returns:
            ZIPファイル用のFileItem
        """
        try:
            # ZIPファイル名を相対パスとして設定
            zip_filename = os.path.basename(zip_path)
            
            # 新しいFileItemを作成
            zip_item = FileItem(
                path=zip_path,
                relative_path=zip_filename,  # tempフォルダ内での相対パス
                name=zip_filename,
                file_type=FileType.FILE,
                item_type=FileItemType.ATTACHMENT  # ZIP化されたファイルは添付ファイル
            )
            
            # ファイルサイズを設定
            if os.path.exists(zip_path):
                zip_item.size = os.path.getsize(zip_path)
            
            print(f"[DEBUG] プレビュー: ZIPアイテム作成 - {zip_item.name} ({zip_item.size} bytes)")
            return zip_item
            
        except Exception as e:
            print(f"[ERROR] プレビュー: ZIP ファイル項目作成エラー: {e}")
            # エラー時はダミーアイテムを返す
            return FileItem(
                path=zip_path or "",
                relative_path=os.path.basename(zip_path) if zip_path else "error.zip",
                name=os.path.basename(zip_path) if zip_path else "error.zip",
                file_type=FileType.FILE,
                item_type=FileItemType.ATTACHMENT
            )
    
    def _get_zip_filename(self, file_item):
        """ファイル項目からZIPファイル名を取得
        
        Args:
            file_item: FileItem
            
        Returns:
            ZIPファイル名（tempフォルダ内のパス）
        """
        try:
            # ファイル項目のパスから相対パスを抽出
            if not file_item.relative_path:
                return None
                
            # ZIP化されたファイルは temp フォルダ内に ZIP として保存される
            base_name = os.path.basename(file_item.relative_path)
            name_without_ext = os.path.splitext(base_name)[0]
            zip_filename = f"{name_without_ext}.zip"
            
            # tempフォルダ内のZIPファイルパス
            temp_dir = os.path.join(os.path.dirname(file_item.path), "temp")
            zip_path = os.path.join(temp_dir, zip_filename)
            
            if os.path.exists(zip_path):
                return zip_path
                
            return None
            
        except Exception as e:
            logger.warning(f"ZIP ファイル名取得でエラー: {e}")
            return None
    
    def _create_zip_file_item(self, original_item, zip_path):
        """ZIPファイル項目の作成
        
        Args:
            original_item: 元のFileItem
            zip_path: ZIPファイルのパス
            
        Returns:
            ZIPファイル用のFileItem
        """
        try:
            # ZIPファイル名を相対パスとして設定
            zip_filename = os.path.basename(zip_path)
            
            # 新しいFileItemを作成
            zip_item = FileItem(
                path=zip_path,
                relative_path=f"temp/{zip_filename}",
                base_path=original_item.base_path,
                file_type=FileType.FILE
            )
            
            return zip_item
            
        except Exception as e:
            logger.warning(f"ZIP ファイル項目作成でエラー: {e}")
            return original_item
    
    def _get_register_filename(self, file_item: FileItem) -> str:
        """登録時のファイル名を取得（複数ファイルセット対応）"""
        try:
            # ファイルアイテムから所属するファイルセットを検索
            target_file_set = None
            for fs in self.file_sets:
                if fs and hasattr(fs, 'get_valid_items'):
                    valid_items = fs.get_valid_items()
                    if file_item in valid_items:
                        target_file_set = fs
                        break
            
            if not target_file_set:
                # ファイルセットが見つからない場合は基本的なファイル名を返す
                return file_item.name or "不明なファイル"
            
            organize_method = getattr(target_file_set, 'organize_method', None)
            if organize_method == PathOrganizeMethod.FLATTEN:
                # フラット化の場合は、相対パスをダブルアンダースコアで置き換え
                relative_path = file_item.relative_path.replace('/', '__').replace('\\', '__')
                return relative_path
            elif organize_method == PathOrganizeMethod.ZIP:
                # ZIP化の場合の表示処理（改善版）
                return self._get_zip_display_filename_for_fileset(file_item, target_file_set)
            else:
                return file_item.relative_path
        except Exception as e:
            print(f"[DEBUG] _get_register_filename エラー: {e}")
            return file_item.name or "不明なファイル"
    
    def _get_zip_display_filename_for_fileset(self, file_item: FileItem, file_set: FileSet) -> str:
        """指定されたファイルセットに対するZIP化されたファイルの表示用ファイル名を取得"""
        try:
            relative_path = Path(file_item.relative_path)
            
            # フォルダのZIP化判定
            if self._is_file_zipped_for_fileset(file_item, file_set):
                # ZIP化されるファイル：ZIPファイル名のみ表示
                if len(relative_path.parts) == 1:
                    # ルート直下のファイル：個別ZIP化
                    return f"{file_item.name}.zip"
                else:
                    # フォルダ内ファイル：フォルダがZIP化される
                    return f"{relative_path.parts[0]}.zip"
            else:
                # ZIP化されないファイル：元ファイル名
                return file_item.name
        except Exception as e:
            print(f"[ERROR] ZIP表示ファイル名取得エラー: {e}")
            return file_item.name or "不明なファイル"
    
    def _get_zip_display_filename(self, file_item: FileItem) -> str:
        """ZIP化されたファイルの表示用ファイル名を取得（旧バージョン、互換性維持）"""
        try:
            # 現在のファイルセットを探す
            target_file_set = None
            for fs in self.file_sets:
                if fs and hasattr(fs, 'get_valid_items'):
                    valid_items = fs.get_valid_items()
                    if file_item in valid_items:
                        target_file_set = fs
                        break
            
            if target_file_set:
                return self._get_zip_display_filename_for_fileset(file_item, target_file_set)
            
            # フォールバック
            relative_path = Path(file_item.relative_path)
            
            # フォルダのZIP化判定（デフォルト）
            if len(relative_path.parts) == 1:
                # ルート直下のファイル：個別ZIP化
                return f"{file_item.name}.zip"
            else:
                # フォルダ内ファイル：フォルダがZIP化される
                return f"{relative_path.parts[0]}.zip"
        except Exception as e:
            print(f"[ERROR] ZIP表示ファイル名取得エラー: {e}")
            return file_item.name or "不明なファイル"
    
    def _is_file_zipped_for_fileset(self, file_item: FileItem, file_set: FileSet) -> bool:
        """指定されたファイルセットに対して、ファイルがZIP化されるかどうかを判定"""
        try:
            # 元からのZIPファイルかチェック
            if file_item.extension and file_item.extension.lower() == '.zip':
                # ベースディレクトリに最初から格納されているZIPファイル
                return False  # そのまま表示
            
            # ZIP化対象ディレクトリを特定
            all_items = file_set.get_valid_items()
            zip_directories = set()
            for item in all_items:
                if item.file_type == FileType.DIRECTORY and getattr(item, 'is_zip', False):
                    zip_directories.add(item.relative_path)
            
            # ファイルがZIP化対象ディレクトリに含まれているかチェック
            relative_path = file_item.relative_path
            for zip_dir in zip_directories:
                if relative_path.startswith(zip_dir + '/') or relative_path.startswith(zip_dir + '\\'):
                    return True
            
            return False
            
        except Exception as e:
            print(f"[ERROR] ファイルZIP化判定エラー: {e}")
            return False
    
    def _is_file_zipped(self, file_item: FileItem) -> bool:
        """ファイルがZIP化されるかどうかを判定（旧バージョン、互換性維持）"""
        try:
            # 現在のファイルセットを探す
            target_file_set = None
            for fs in self.file_sets:
                if fs and hasattr(fs, 'get_valid_items'):
                    valid_items = fs.get_valid_items()
                    if file_item in valid_items:
                        target_file_set = fs
                        break
            
            if target_file_set:
                return self._is_file_zipped_for_fileset(file_item, target_file_set)
            
            # フォールバック: 元からのZIPファイルかチェック
            if file_item.extension and file_item.extension.lower() == '.zip':
                return False  # そのまま表示
            
            # デフォルトはZIP化されない
            return False
            
        except Exception as e:
            print(f"[ERROR] ファイルZIP化判定エラー: {e}")
            return False
    
    def _get_file_type_category(self, file_item: FileItem) -> str:
        """ファイルの種別（データファイル/添付ファイル）を取得"""
        # 拡張子ベースでの簡易判定
        data_extensions = {'.csv', '.xlsx', '.xls', '.txt', '.dat', '.json', '.xml'}
        
        try:
            if file_item.extension and file_item.extension.lower() in data_extensions:
                return "データファイル"
            else:
                return "添付ファイル"
        except:
            return "不明"

    def _on_file_type_changed(self, text: str, file_item: FileItem):
        """ファイル種別変更時の処理"""
        try:
            # ファイルアイテムのitem_typeを設定
            if text == "添付ファイル":
                file_item.item_type = FileItemType.ATTACHMENT
            else:
                file_item.item_type = FileItemType.DATA
                
            print(f"[DEBUG] ファイル種別変更: {file_item.name} → {text} ({file_item.item_type})")
            
            # マッピングファイルを再作成（必要に応じて）
            # self._recreate_mapping_file()
            
        except Exception as e:
            print(f"[ERROR] ファイル種別変更処理エラー: {e}")

    def _recreate_mapping_file(self):
        """マッピングファイルを再作成"""
        try:
            # 一時フォルダ管理クラスを使用してマッピングファイルを再作成
            from ..core.temp_folder_manager import TempFolderManager
            
            temp_folder = getattr(self.file_set, 'temp_folder', None)
            extended_config = getattr(self.file_set, 'extended_config', {})
            if not temp_folder and 'temp_folder' in extended_config:
                temp_folder = extended_config['temp_folder']
            
            if temp_folder and os.path.exists(temp_folder):
                temp_manager = TempFolderManager()
                
                # ファイルセットの一時フォルダ情報を更新
                temp_manager.temp_folders[self.file_set.id] = temp_folder
                
                # 現在のファイル種別設定を反映してマッピングファイルを再作成
                if self.file_set.organize_method == PathOrganizeMethod.FLATTEN:
                    mapping_file = temp_manager._create_flatten_structure(self.file_set, temp_folder)
                else:
                    mapping_file = temp_manager._create_zip_structure(self.file_set, temp_folder)
                
                # ファイルセットのマッピングファイル情報を更新
                self.file_set.mapping_file = mapping_file
                if hasattr(self.file_set, 'extended_config'):
                    self.file_set.extended_config['mapping_file'] = mapping_file
                
                print(f"[INFO] マッピングファイルを再作成: {mapping_file}")
                
        except Exception as e:
            print(f"[ERROR] マッピングファイル再作成エラー: {e}")
    
    def _open_temp_folder(self):
        """一時フォルダを開く"""
        try:
            temp_folder = getattr(self.file_set, 'temp_folder', None)
            
            # 拡張設定からも一時フォルダ情報を確認
            extended_config = getattr(self.file_set, 'extended_config', {})
            if not temp_folder and 'temp_folder' in extended_config:
                temp_folder = extended_config['temp_folder']
            
            if temp_folder and os.path.exists(temp_folder):
                import subprocess
                import platform
                
                if platform.system() == "Windows":
                    subprocess.run(["explorer", temp_folder])
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", temp_folder])
                else:  # Linux
                    subprocess.run(["xdg-open", temp_folder])
            else:
                QMessageBox.warning(self, "警告", "一時フォルダが存在しません。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"一時フォルダを開く際にエラーが発生しました:\n{str(e)}")
    
    def _open_mapping_file(self):
        """マッピングファイルを開く"""
        try:
            # まず最新の状態でマッピングファイルを再作成
            self._recreate_mapping_file()
            
            mapping_file = getattr(self.file_set, 'mapping_file', None)
            
            # 拡張設定からも一時フォルダ情報を確認
            extended_config = getattr(self.file_set, 'extended_config', {})
            if not mapping_file and 'mapping_file' in extended_config:
                mapping_file = extended_config['mapping_file']
            
            if mapping_file and os.path.exists(mapping_file):
                import subprocess
                import platform
                
                if platform.system() == "Windows":
                    subprocess.run(["start", mapping_file], shell=True)
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", mapping_file])
                else:  # Linux
                    subprocess.run(["xdg-open", mapping_file])
                    
                print(f"[INFO] マッピングファイルを開きました: {mapping_file}")
            else:
                QMessageBox.warning(self, "警告", "マッピングファイルが存在しません。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"マッピングファイルを開く際にエラーが発生しました:\n{str(e)}")
    
    def _update_mapping_file(self):
        """マッピングファイルを更新"""
        try:
            from ..core.temp_folder_manager import TempFolderManager
            
            temp_manager = TempFolderManager()
            
            # 既存の一時フォルダを確認
            temp_folder = getattr(self.file_set, 'temp_folder', None)
            extended_config = getattr(self.file_set, 'extended_config', {})
            if not temp_folder and 'temp_folder' in extended_config:
                temp_folder = extended_config['temp_folder']
            
            # 一時フォルダが存在しない場合は新規作成
            if not temp_folder or not os.path.exists(temp_folder):
                temp_folder, mapping_file = temp_manager.create_temp_folder_for_fileset(self.file_set)
                # ファイルセットに一時フォルダ情報を設定
                if not hasattr(self.file_set, 'extended_config'):
                    self.file_set.extended_config = {}
                self.file_set.extended_config['temp_folder'] = temp_folder
                self.file_set.extended_config['temp_created'] = True
                self.file_set.extended_config['mapping_file'] = mapping_file
                self.file_set.mapping_file = mapping_file
            else:
                # 既存の一時フォルダでマッピングファイルを更新
                temp_manager.temp_folders[self.file_set.id] = temp_folder
                
                if self.file_set.organize_method == PathOrganizeMethod.FLATTEN:
                    mapping_file = temp_manager._create_flatten_structure(self.file_set, temp_folder)
                else:
                    mapping_file = temp_manager._create_zip_structure(self.file_set, temp_folder)
                
                # ファイルセットのマッピングファイル情報を更新
                self.file_set.extended_config['mapping_file'] = mapping_file
                self.file_set.mapping_file = mapping_file
            
            # UIを更新
            self._update_temp_folder_buttons()
            self._load_settings_info()
            
            QMessageBox.information(self, "完了", 
                f"マッピングファイルを更新しました。\n"
                f"パス: {mapping_file}")
                
        except Exception as e:
            print(f"[ERROR] マッピングファイル更新エラー: {e}")
            QMessageBox.warning(self, "エラー", f"マッピングファイルの更新に失敗しました: {str(e)}")
    
    def _export_fileset_folder(self):
        """ファイルセットフォルダを書き出し"""
        try:
            # 一時フォルダが存在しない場合は先に作成
            temp_folder = getattr(self.file_set, 'temp_folder', None)
            extended_config = getattr(self.file_set, 'extended_config', {})
            if not temp_folder and 'temp_folder' in extended_config:
                temp_folder = extended_config['temp_folder']
            
            if not temp_folder or not os.path.exists(temp_folder):
                # 一時フォルダを作成
                from ..core.temp_folder_manager import TempFolderManager
                temp_manager = TempFolderManager()
                temp_folder, mapping_file = temp_manager.create_temp_folder_for_fileset(self.file_set)
                
                if not hasattr(self.file_set, 'extended_config'):
                    self.file_set.extended_config = {}
                self.file_set.extended_config['temp_folder'] = temp_folder
                self.file_set.extended_config['temp_created'] = True
                self.file_set.extended_config['mapping_file'] = mapping_file
                self.file_set.mapping_file = mapping_file
            
            # 保存先を選択
            from PyQt5.QtWidgets import QMessageBox
            
            
            # カスタムボタンテキストを設定
            msgbox = QMessageBox(self)
            msgbox.setWindowTitle("書き出し形式選択")
            msgbox.setText("ファイルセットの書き出し形式を選択してください。")
            
            folder_btn = msgbox.addButton("フォルダとして", QMessageBox.ActionRole)
            zip_btn = msgbox.addButton("ZIPファイルとして", QMessageBox.ActionRole)
            cancel_btn = msgbox.addButton("キャンセル", QMessageBox.RejectRole)
            
            msgbox.exec_()
            clicked_button = msgbox.clickedButton()
            
            if clicked_button == cancel_btn:
                return
                
            export_as_zip = (clicked_button == zip_btn)
            
            # 保存先を選択
            if export_as_zip:
                from PyQt5.QtWidgets import QFileDialog
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "ZIPファイル保存先", 
                    f"{self.file_set.name}.zip",
                    "ZIPファイル (*.zip)"
                )
                if not file_path:
                    return
                
                # ZIPファイルとして保存
                import shutil
                shutil.make_archive(file_path[:-4], 'zip', temp_folder)
                
                QMessageBox.information(self, "完了", 
                    f"ファイルセット '{self.file_set.name}' をZIPファイルとして保存しました。\n"
                    f"パス: {file_path}")
            else:
                from PyQt5.QtWidgets import QFileDialog
                folder_path = QFileDialog.getExistingDirectory(
                    self, "フォルダ保存先", ""
                )
                if not folder_path:
                    return
                
                # フォルダとして保存
                import shutil
                dest_folder = os.path.join(folder_path, self.file_set.name)
                shutil.copytree(temp_folder, dest_folder, dirs_exist_ok=True)
                
                QMessageBox.information(self, "完了", 
                    f"ファイルセット '{self.file_set.name}' をフォルダとして保存しました。\n"
                    f"パス: {dest_folder}")
                
        except Exception as e:
            print(f"[ERROR] フォルダ書き出しエラー: {e}")
            QMessageBox.warning(self, "エラー", f"フォルダ書き出しに失敗しました: {str(e)}")
    
    def _update_temp_folder_buttons(self):
        """一時フォルダボタンの表示状態を更新"""
        try:
            temp_folder = getattr(self.file_set, 'temp_folder', None)
            mapping_file = getattr(self.file_set, 'mapping_file', None)
            
            # 拡張設定からも一時フォルダ情報を確認
            extended_config = getattr(self.file_set, 'extended_config', {})
            if not temp_folder and 'temp_folder' in extended_config:
                temp_folder = extended_config['temp_folder']
            if not mapping_file and 'mapping_file' in extended_config:
                mapping_file = extended_config['mapping_file']
            
            # 一時フォルダボタンの有効/無効
            if temp_folder and os.path.exists(temp_folder):
                self.open_temp_folder_button.setEnabled(True)
                self.open_temp_folder_button.setText(f"一時フォルダを開く")
            else:
                self.open_temp_folder_button.setEnabled(False)
                self.open_temp_folder_button.setText("一時フォルダなし")
            
            # マッピングファイルボタンの有効/無効（修正版）
            if mapping_file and os.path.exists(mapping_file):
                self.open_mapping_file_button.setEnabled(True)
                self.open_mapping_file_button.setText("マッピングファイルを開く")
            else:
                self.open_mapping_file_button.setEnabled(False)
                self.open_mapping_file_button.setText("マッピングファイルなし")
                
        except Exception as e:
            print(f"[WARNING] ボタン状態更新エラー: {e}")
            self.open_temp_folder_button.setEnabled(False)
            self.open_temp_folder_button.setText("一時フォルダなし")
            self.open_mapping_file_button.setEnabled(False)
            self.open_mapping_file_button.setText("マッピングファイルなし")
    
    def _get_sample_mode_display(self) -> str:
        """試料モードの表示名を取得"""
        try:
            # 直接の属性から取得を試行
            sample_mode = getattr(self.file_set, 'sample_mode', None)
            
            print(f"[DEBUG] _get_sample_mode_display - 直接属性: sample_mode={sample_mode}")
            
            # 属性ベースの変換を優先
            if sample_mode:
                mode_map = {
                    "new": "新規作成",
                    "existing": "既存試料使用", 
                    "same_as_previous": "前回と同じ"
                }
                display_mode = mode_map.get(sample_mode, sample_mode)
                print(f"[DEBUG] _get_sample_mode_display - 属性ベース変換: {sample_mode} -> {display_mode}")
                return display_mode
            
            # 属性にない場合は拡張設定から取得
            extended_config = getattr(self.file_set, 'extended_config', {})
            sample_mode_text = extended_config.get('sample_mode', '新規作成')
            
            print(f"[DEBUG] _get_sample_mode_display - 拡張設定: sample_mode_text={sample_mode_text}")
            
            # テキストベースで判定
            if sample_mode_text == "既存試料使用":
                return "既存試料使用"
            elif sample_mode_text == "前回と同じ":
                return "前回と同じ"
            else:
                return "新規作成"
                
        except Exception as e:
            print(f"[ERROR] _get_sample_mode_display エラー: {e}")
            return "未設定"
    
    def _format_size(self, size_bytes: int) -> str:
        """ファイルサイズを人間が読みやすい形式に変換"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)
        while size >= 1024 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.1f} {size_names[i]}"
    
    def _get_mapping_file_path(self) -> Optional[str]:
        """マッピングファイルのパスを取得"""
        try:
            # 直接的な属性をチェック
            mapping_file = getattr(self.file_set, 'mapping_file_path', None)
            
            # 後方互換性：旧形式も確認
            if not mapping_file:
                mapping_file = getattr(self.file_set, 'mapping_file', None)
            
            # 拡張設定からも確認
            if not mapping_file:
                extended_config = getattr(self.file_set, 'extended_config', {})
                mapping_file = extended_config.get('mapping_file')
            
            # ファイルの存在確認
            if mapping_file and os.path.exists(mapping_file):
                return mapping_file
            
            # 一時フォルダから推測
            temp_folder = getattr(self.file_set, 'temp_folder', None)
            if not temp_folder:
                extended_config = getattr(self.file_set, 'extended_config', {})
                temp_folder = extended_config.get('temp_folder')
            
            if temp_folder and os.path.exists(temp_folder):
                mapping_path = os.path.join(temp_folder, "path_mapping.xlsx")
                if os.path.exists(mapping_path):
                    return mapping_path
            
            return None
            
        except Exception as e:
            print(f"[WARNING] マッピングファイルパス取得エラー: {e}")
            return None

    def _upload_file(self, file_item: FileItem):
        """ファイルアップロード処理（改良版：デバッグ情報表示・確認ダイアログ付き）"""
        try:
            print(f"[DEBUG] _upload_file 開始: {file_item.name}")
            print(f"[DEBUG] ファイルパス: {file_item.path}")
            
            if not os.path.exists(file_item.path):
                print(f"[ERROR] ファイルが存在しません: {file_item.path}")
                QMessageBox.warning(self, "エラー", f"ファイルが存在しません: {file_item.path}")
                return
            
            # データセットIDを取得
            dataset_id = getattr(self.file_set, 'dataset_id', None)
            print(f"[DEBUG] データセットID: {dataset_id}")
            if not dataset_id:
                print(f"[ERROR] データセットが選択されていません")
                QMessageBox.warning(self, "エラー", "データセットが選択されていません")
                return
                
            # ファイル情報を取得
            filename = os.path.basename(file_item.path)
            encoded_filename = urllib.parse.quote(filename)
            file_size = os.path.getsize(file_item.path)
            
            # APIエンドポイントとヘッダー情報を準備
            # v1.18.4: Bearer Tokenはapi_request_helperが自動選択するため、Authorizationヘッダーは不要
            url = f"https://rde-entry-api-arim.nims.go.jp/uploads?datasetId={dataset_id}"
            headers = {
                "Accept": "application/json",
                "X-File-Name": encoded_filename,
                "User-Agent": "PythonUploader/1.0",
            }
            
            # リクエスト情報を表示する確認ダイアログ
            request_info = f"""【アップロード実行確認】

ファイル情報:
  ファイル名: {filename}
  ファイルサイズ: {self._format_size(file_size)}
  ファイルパス: {file_item.path}

API情報:
  エンドポイント: {url}
  データセットID: {dataset_id}
  
認証情報:
  自動選択されます（URLから適切なトークンを選択）
  
リクエストヘッダー:
  Accept: {headers["Accept"]}
  Content-Type: application/octet-stream (自動設定)
  X-File-Name: {headers["X-File-Name"]}
  User-Agent: {headers["User-Agent"]}

このファイルをアップロードしますか？"""
            
            # 確認ダイアログを表示
            reply = QMessageBox.question(
                self, "アップロード確認", request_info,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                print("[INFO] ユーザーがアップロードをキャンセルしました")
                return
            
            print(f"[INFO] アップロード開始: {filename} ({self._format_size(file_size)})")
            print(f"[INFO] API URL: {url}")
            print(f"[INFO] エンコード済みファイル名: {encoded_filename}")
            
            # プログレスダイアログ
            progress = QProgressDialog("ファイルをアップロード中...", "キャンセル", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            
            try:
                # 改良されたアップロード処理を実行（v1.18.4: bearer_token削除）
                upload_result = self._execute_upload_with_debug(
                    dataset_id, file_item.path, headers, url
                )
                
                if upload_result and upload_result.get('upload_id'):
                    upload_id = upload_result['upload_id']
                    response_data = upload_result.get('response_data', {})
                    
                    # ファイルアイテムにアップロードIDを記録
                    setattr(file_item, 'upload_id', upload_id)
                    setattr(file_item, 'upload_response', response_data)
                    print(f"[SUCCESS] ファイルにアップロードID記録: {file_item.name} -> {upload_id}")
                    
                    # 成功ダイアログでレスポンス情報も表示
                    success_message = f"""ファイルアップロードが完了しました

ファイル情報:
  ファイル名: {file_item.name}
  サイズ: {self._format_size(file_size)}

アップロード結果:
  アップロードID: {upload_id}
  レスポンスサイズ: {len(str(response_data))} 文字
  
レスポンス詳細:
{str(response_data)[:500]}{'...' if len(str(response_data)) > 500 else ''}"""
                    
                    QMessageBox.information(self, "アップロード成功", success_message)
                    print(f"[SUCCESS] アップロード完了: {file_item.name} -> ID: {upload_id}")
                    
                else:
                    error_detail = upload_result.get('error', '不明なエラー') if upload_result else '戻り値がありません'
                    print(f"[ERROR] アップロード失敗: {error_detail}")
                    QMessageBox.warning(self, "アップロード失敗", f"ファイルアップロードに失敗しました\n\nエラー詳細:\n{error_detail}")
                    
            finally:
                progress.close()
                
        except Exception as e:
            print(f"[ERROR] アップロード処理中にエラー: {e}")
            import traceback
            print(f"[ERROR] スタックトレース:\n{traceback.format_exc()}")
            QMessageBox.critical(self, "エラー", f"アップロード処理中にエラーが発生しました: {e}")
    
    def _execute_upload_with_debug(self, dataset_id, file_path, headers, url):
        """
        デバッグ機能付きアップロード実行
        v1.18.4: Bearer Token自動選択対応、api_request_helper使用に変更
        """
        try:
            print(f"[DEBUG] _execute_upload_with_debug 開始")
            print(f"[DEBUG] ファイルパス: {file_path}")
            print(f"[DEBUG] データセットID: {dataset_id}")
            
            # ファイルを読み込み
            with open(file_path, 'rb') as f:
                binary_data = f.read()
            
            file_size = len(binary_data)
            filename = os.path.basename(file_path)
            encoded_filename = urllib.parse.quote(filename)
            print(f"[DEBUG] ファイルサイズ (バイナリ): {file_size} bytes")
            print(f"[DEBUG] オリジナルファイル名: {filename}")
            print(f"[DEBUG] エンコード済みファイル名: {encoded_filename}")
            
            # ヘッダー準備（v1.18.4: Authorizationヘッダーは自動設定されるため除外）
            actual_headers = {
                "Accept": "application/json",
                "X-File-Name": encoded_filename,
                "User-Agent": "PythonUploader/1.0",
            }
            
            print(f"[DEBUG] API呼び出し開始: POST {url}")
            print(f"[DEBUG] リクエストヘッダー数: {len(actual_headers)}")
            print(f"[DEBUG] X-File-Name: {actual_headers['X-File-Name']}")
            print(f"[DEBUG] バイナリデータサイズ: {len(binary_data)} bytes")
            print(f"[DEBUG] Bearer Token: URLから自動選択されます")
            
            # v1.18.4: api_request_helper.post_binaryを使用（Bearer Token自動選択）
            from classes.utils.api_request_helper import post_binary
            
            resp = post_binary(
                url=url,
                data=binary_data,
                bearer_token=None,  # 自動選択させる
                content_type='application/octet-stream',
                headers=actual_headers,
                timeout=60  # アップロードは時間がかかる可能性があるため60秒に設定
            )
            
            if resp is None:
                print(f"[ERROR] API呼び出し失敗: レスポンスがNone")
                return {"error": "API呼び出し失敗: レスポンスがありません"}
            
            print(f"[DEBUG] レスポンス受信: ステータスコード {resp.status_code}")
            print(f"[DEBUG] レスポンスヘッダー: {dict(resp.headers)}")
            
            # ステータスコードチェック（200番台は成功）
            if not (200 <= resp.status_code < 300):
                error_text = resp.text[:500] if hasattr(resp, 'text') else 'レスポンステキストなし'
                print(f"[ERROR] HTTPエラー: {resp.status_code}")
                print(f"[ERROR] レスポンス内容: {error_text}")
                
                # 502エラーの場合の詳細情報
                if resp.status_code == 502:
                    print(f"[ERROR] 502 Bad Gateway - サーバー側の問題またはリクエスト形式の問題")
                    print(f"[ERROR] ファイルサイズ制限チェック: {file_size} bytes")
                    print(f"[ERROR] Content-Type確認: {actual_headers.get('Content-Type')}")
                    print(f"[ERROR] X-File-Name確認: {actual_headers.get('X-File-Name')}")
                
                return {"error": f"HTTP {resp.status_code}: {error_text}"}
            
            print(f"[SUCCESS] HTTPレスポンス成功: {resp.status_code}")
            
            # JSONレスポンスをパース
            try:
                response_data = resp.json()
                print(f"[DEBUG] JSONパース成功: {len(str(response_data))} 文字")
                print(f"[DEBUG] レスポンス構造: {list(response_data.keys()) if isinstance(response_data, dict) else type(response_data)}")
            except Exception as json_error:
                print(f"[ERROR] JSONパースエラー: {json_error}")
                print(f"[ERROR] レスポンステキスト: {resp.text[:200]}")
                return {"error": f"JSONパースエラー: {json_error}"}
            
            # uploadIdを抽出
            upload_id = response_data.get("uploadId")
            if not upload_id:
                print(f"[ERROR] uploadIdがレスポンスに含まれていません")
                print(f"[ERROR] レスポンス内容: {response_data}")
                return {"error": "レスポンスにuploadIdが含まれていません", "response_data": response_data}
            
            print(f"[SUCCESS] アップロードID取得成功: {upload_id}")
            
            # レスポンスをファイルに保存（デバッグ用）
            try:
                from config.common import OUTPUT_RDE_DIR
                output_dir = os.path.join(OUTPUT_RDE_DIR, "data")
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, f"upload_response_{upload_id}.json")
                import json
                with open(output_path, "w", encoding="utf-8") as outf:
                    json.dump(response_data, outf, ensure_ascii=False, indent=2)
                print(f"[DEBUG] レスポンスファイル保存: {output_path}")
            except Exception as save_error:
                print(f"[WARNING] レスポンスファイル保存エラー: {save_error}")
            
            return {
                "upload_id": upload_id,
                "response_data": response_data,
                "status_code": resp.status_code,
                "response_headers": dict(resp.headers)
            }
            
        except Exception as e:
            print(f"[ERROR] _execute_upload_with_debug エラー: {e}")
            import traceback
            print(f"[ERROR] スタックトレース:\n{traceback.format_exc()}")
            return {"error": str(e)}
            print(f"[ERROR] ファイルアップロードエラー: {e}")
    
    def _batch_upload_files(self):
        """ファイル一括アップロード処理"""
        try:
            print("[INFO] ファイル一括アップロード処理開始")
            
            # 前提条件チェック
            if not self._validate_upload_prerequisites():
                return
            
            # 確認ダイアログ
            reply = QMessageBox.question(
                self, "ファイル一括アップロード確認", 
                "ファイル一括アップロードを実行しますか？\n\n"
                "処理には時間がかかる場合があります。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                print("[INFO] ユーザーがアップロードをキャンセルしました")
                return
            
            # アップロード実行
            upload_success = self._execute_batch_upload()
            
            if upload_success:
                QMessageBox.information(self, "完了", "ファイル一括アップロードが正常に完了しました。")
            else:
                QMessageBox.warning(self, "エラー", "ファイル一括アップロードに失敗しました。詳細はログを確認してください。")
            
        except Exception as e:
            print(f"[ERROR] ファイル一括アップロード処理エラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"ファイル一括アップロード処理でエラーが発生しました:\n{str(e)}")

    def _validate_upload_prerequisites(self) -> bool:
        """ファイルアップロードの前提条件をチェック（Bearer Token自動選択対応）"""
        try:
            # 注意: Bearer Tokenは不要（API呼び出し時に自動選択される）
            # このチェックではファイルセットとデータセットIDのみ確認
            
            # ファイルセット確認
            if not hasattr(self, 'file_set') or not self.file_set:
                QMessageBox.warning(self, "エラー", "ファイルセットが選択されていません。")
                return False
            
            # データセット情報確認（複数の場所をチェック）
            dataset_info = getattr(self.file_set, 'dataset_info', None)
            extended_config = getattr(self.file_set, 'extended_config', {})
            dataset_id = None
            
            # データセットIDの取得（優先順位：1. dataset_info, 2. fileset.dataset_id, 3. extended_config）
            if dataset_info and dataset_info.get('id'):
                dataset_id = dataset_info['id']
                print(f"[DEBUG] dataset_infoからデータセットID取得: {dataset_id}")
            elif hasattr(self.file_set, 'dataset_id') and self.file_set.dataset_id:
                dataset_id = self.file_set.dataset_id
                print(f"[DEBUG] fileset.dataset_idからデータセットID取得: {dataset_id}")
            elif extended_config.get('dataset_id'):
                dataset_id = extended_config['dataset_id']
                print(f"[DEBUG] extended_configからデータセットID取得: {dataset_id}")
                
            # dataset_infoが不足している場合、データセットファイルから読み込み
            if dataset_id and not dataset_info:
                try:
                    from config.common import OUTPUT_RDE_DIR
                    dataset_file_path = os.path.join(OUTPUT_RDE_DIR, "data", "datasets", f"{dataset_id}.json")
                    if os.path.exists(dataset_file_path):
                        with open(dataset_file_path, 'r', encoding='utf-8') as f:
                            dataset_data = json.load(f)
                        # dataset_infoとしてfile_setに設定
                        self.file_set.dataset_info = dataset_data
                        dataset_info = dataset_data
                        print(f"[DEBUG] データセット情報をファイルから復元: {dataset_data.get('attributes', {}).get('name', dataset_id)}")
                    else:
                        print(f"[WARNING] データセットファイルが見つかりません: {dataset_file_path}")
                except Exception as e:
                    print(f"[WARNING] データセット情報復元エラー: {e}")
            
            if not dataset_id:
                # デバッグ情報を詳細に出力
                print("[DEBUG] データセットID取得失敗 - 詳細情報:")
                print(f"[DEBUG] - hasattr(file_set, 'dataset_id'): {hasattr(self.file_set, 'dataset_id')}")
                print(f"[DEBUG] - file_set.dataset_id: {getattr(self.file_set, 'dataset_id', 'NONE')}")
                print(f"[DEBUG] - dataset_info: {dataset_info}")
                print(f"[DEBUG] - extended_config keys: {list(extended_config.keys()) if extended_config else 'NONE'}")
                print(f"[DEBUG] - extended_config.dataset_id: {extended_config.get('dataset_id', 'NONE')}")
                QMessageBox.warning(self, "エラー", "データセット情報が設定されていません。")
                return False
            
            # ファイル存在確認
            valid_items = self.file_set.get_valid_items()
            file_items = [item for item in valid_items if item.file_type == FileType.FILE]
            display_items = self._get_display_file_items(file_items)
            
            if not display_items:
                QMessageBox.warning(self, "エラー", "アップロード対象のファイルがありません。")
                return False
            
            # ファイル存在確認
            missing_files = []
            for item in display_items:
                if not os.path.exists(item.path):
                    missing_files.append(item.name)
            
            if missing_files:
                QMessageBox.warning(self, "エラー", 
                    f"以下のファイルが見つかりません:\n" + "\n".join(missing_files[:5]) +
                    (f"\n... 他{len(missing_files) - 5}件" if len(missing_files) > 5 else ""))
                return False
            
            print(f"[INFO] アップロード前提条件チェック完了: ファイル={len(display_items)}個")
            return True
            
        except Exception as e:
            print(f"[ERROR] アップロード前提条件チェックエラー: {e}")
            QMessageBox.critical(self, "エラー", f"前提条件の確認でエラーが発生しました:\n{str(e)}")
            return False
    
    def _validate_registration_prerequisites(self) -> bool:
        """データ登録の前提条件をチェック"""
        try:
            # ベアラートークン確認（個別アップロードと同じロジック）
            bearer_token = getattr(self, 'bearer_token', None)
            if not bearer_token:
                print("[DEBUG] Bearer トークンが親から取得できない - 他の方法を試行")
                
                # 親ウィジェットから取得を試行（複数階層遡及）
                current_widget = self
                while current_widget and not bearer_token:
                    current_widget = current_widget.parent()
                    if current_widget and hasattr(current_widget, 'bearer_token'):
                        bearer_token = current_widget.bearer_token
                        print(f"[DEBUG] 親ウィジェット({type(current_widget).__name__})からBearerトークンを取得")
                        break
                
                # まだない場合は、メインコントローラから取得を試行
                if not bearer_token:
                    try:
                        from PyQt5.QtWidgets import QApplication
                        app = QApplication.instance()
                        if app:
                            main_window = None
                            for widget in app.topLevelWidgets():
                                if hasattr(widget, 'controller') and hasattr(widget.controller, 'bearer_token'):
                                    bearer_token = widget.controller.bearer_token
                                    print("[DEBUG] メインコントローラからBearerトークンを取得")
                                    break
                    except Exception as e:
                        print(f"[WARNING] メインコントローラからのトークン取得エラー: {e}")
                
                # それでもない場合はファイルから読み取り
                if not bearer_token:
                    print("[DEBUG] ファイルからBearerトークンを読み取り試行")
                    from config.common import BEARER_TOKEN_FILE
                    try:
                        if os.path.exists(BEARER_TOKEN_FILE):
                            with open(BEARER_TOKEN_FILE, 'r', encoding='utf-8') as f:
                                file_token = f.read().strip()
                            # ファイルから読み取ったトークンの形式をチェック
                            if file_token and file_token.startswith('Bearer '):
                                bearer_token = file_token[7:]  # 'Bearer 'プレフィックスを除去
                            elif file_token:
                                bearer_token = file_token
                            print(f"[DEBUG] ファイルからBearerトークンを取得: 長さ={len(bearer_token) if bearer_token else 0}")
                    except Exception as e:
                        print(f"[WARNING] Bearerトークンファイル読み取りエラー: {e}")
            
            if not bearer_token:
                print("[ERROR] Bearerトークンが取得できません")
                QMessageBox.warning(self, "エラー", "認証トークンが設定されていません。ログインを確認してください。")
                return False
            
            # トークンの形式をチェック・清浄化
            bearer_token = bearer_token.strip()
            
            # 様々なプレフィックスを除去
            if bearer_token.startswith('BearerToken='):
                bearer_token = bearer_token[12:]  # 'BearerToken='プレフィックスを除去
            elif bearer_token.startswith('Bearer '):
                bearer_token = bearer_token[7:]  # 'Bearer 'プレフィックスを除去
            
            print(f"[DEBUG] データ登録前提条件チェック - 取得したトークン: 長さ={len(bearer_token)}, 先頭10文字={bearer_token[:10]}")
            
            # 取得したトークンをインスタンス変数に保存（後続処理で使用）
            self.bearer_token = bearer_token
            
            # ファイルセット確認
            if not hasattr(self, 'file_set') or not self.file_set:
                QMessageBox.warning(self, "エラー", "ファイルセットが選択されていません。")
                return False
            
            # データセット情報確認（複数の場所をチェック）
            dataset_info = getattr(self.file_set, 'dataset_info', None)
            extended_config = getattr(self.file_set, 'extended_config', {})
            dataset_id = None
            
            # データセットIDの取得（優先順位：1. dataset_info, 2. fileset.dataset_id, 3. extended_config）
            if dataset_info and dataset_info.get('id'):
                dataset_id = dataset_info['id']
                print(f"[DEBUG] dataset_infoからデータセットID取得: {dataset_id}")
            elif hasattr(self.file_set, 'dataset_id') and self.file_set.dataset_id:
                dataset_id = self.file_set.dataset_id
                print(f"[DEBUG] fileset.dataset_idからデータセットID取得: {dataset_id}")
            elif extended_config.get('dataset_id'):
                dataset_id = extended_config['dataset_id']
                print(f"[DEBUG] extended_configからデータセットID取得: {dataset_id}")
                
            # dataset_infoが不足している場合、データセットファイルから読み込み
            if dataset_id and not dataset_info:
                try:
                    from config.common import OUTPUT_RDE_DIR
                    dataset_file_path = os.path.join(OUTPUT_RDE_DIR, "data", "datasets", f"{dataset_id}.json")
                    if os.path.exists(dataset_file_path):
                        with open(dataset_file_path, 'r', encoding='utf-8') as f:
                            dataset_data = json.load(f)
                        # dataset_infoとしてfile_setに設定
                        self.file_set.dataset_info = dataset_data
                        dataset_info = dataset_data
                        print(f"[DEBUG] データセット情報をファイルから復元: {dataset_data.get('attributes', {}).get('name', dataset_id)}")
                    else:
                        print(f"[WARNING] データセットファイルが見つかりません: {dataset_file_path}")
                except Exception as e:
                    print(f"[WARNING] データセット情報復元エラー: {e}")
            
            if not dataset_id:
                # デバッグ情報を詳細に出力
                print("[DEBUG] データセットID取得失敗 - 詳細情報:")
                print(f"[DEBUG] - hasattr(file_set, 'dataset_id'): {hasattr(self.file_set, 'dataset_id')}")
                print(f"[DEBUG] - file_set.dataset_id: {getattr(self.file_set, 'dataset_id', 'NONE')}")
                print(f"[DEBUG] - dataset_info: {dataset_info}")
                print(f"[DEBUG] - extended_config keys: {list(extended_config.keys()) if extended_config else 'NONE'}")
                print(f"[DEBUG] - extended_config.dataset_id: {extended_config.get('dataset_id', 'NONE')}")
                QMessageBox.warning(self, "エラー", "データセット情報が設定されていません。")
                return False
            
            # ファイル存在確認
            valid_items = self.file_set.get_valid_items()
            file_items = [item for item in valid_items if item.file_type == FileType.FILE]
            display_items = self._get_display_file_items(file_items)
            
            if not display_items:
                QMessageBox.warning(self, "エラー", "登録対象のファイルがありません。")
                return False
            
            # ファイル存在確認
            missing_files = []
            for item in display_items:
                if not os.path.exists(item.path):
                    missing_files.append(item.name)
            
            if missing_files:
                QMessageBox.warning(self, "エラー", 
                    f"以下のファイルが見つかりません:\n" + "\n".join(missing_files[:5]) +
                    (f"\n... 他{len(missing_files) - 5}件" if len(missing_files) > 5 else ""))
                return False
            
            print(f"[INFO] データ登録前提条件チェック完了: ファイル={len(display_items)}個")
            return True
            
        except Exception as e:
            print(f"[ERROR] データ登録前提条件チェックエラー: {e}")
            QMessageBox.critical(self, "エラー", f"前提条件の確認でエラーが発生しました:\n{str(e)}")
            return False
    
    def _batch_register_data(self):
        """データ登録処理（ファイル一括アップロード + データ登録）"""
        try:
            print("[INFO] データ登録処理開始")
            
            # 前提条件チェック
            if not self._validate_registration_prerequisites():
                return
            
            # 確認ダイアログ
            reply = QMessageBox.question(
                self, "データ登録確認", 
                "データ登録を実行しますか？\n\n"
                "この処理では以下が実行されます：\n"
                "1. ファイル一括アップロード\n"
                "2. データエントリー登録\n"
                "3. 試料情報の保存\n\n"
                "処理には時間がかかる場合があります。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                print("[INFO] ユーザーがデータ登録をキャンセルしました")
                return
            
            # 段階1: ファイル一括アップロード
            print("[INFO] 段階1: ファイル一括アップロード")
            upload_success = self._execute_batch_upload()
            
            if not upload_success:
                QMessageBox.warning(self, "エラー", "ファイルアップロードに失敗したため、データ登録を中断します。")
                return
            
            # 段階2: データ登録実行
            print("[INFO] 段階2: データ登録実行")
            registration_success = self._execute_data_registration()
            
            if registration_success:
                QMessageBox.information(self, "完了", "データ登録が正常に完了しました。")
            else:
                QMessageBox.warning(self, "エラー", "データ登録に失敗しました。詳細はログを確認してください。")
            
        except Exception as e:
            print(f"[ERROR] データ登録処理エラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"データ登録処理でエラーが発生しました:\n{str(e)}")
    
    def _build_form_values_from_fileset(self):
        """ファイルセットからフォーム値を構築"""
        try:
            print(f"[DEBUG] _build_form_values_from_fileset開始 - ファイルセット: {self.file_set.name}")
            
            # 基本情報
            form_values = {
                'dataName': getattr(self.file_set, 'data_name', '') or f"Data_{self.file_set.name}",
                'basicDescription': getattr(self.file_set, 'description', '') or "一括登録によるデータ",
                'experimentId': getattr(self.file_set, 'experiment_id', '') or '',
                'referenceUrl': getattr(self.file_set, 'reference_url', '') or '',
                'tags': getattr(self.file_set, 'tags', '') or '',
            }
            
            # デバッグ：ファイルセットの内容確認
            extended_config = getattr(self.file_set, 'extended_config', {})
            print(f"[DEBUG] ファイルセット内容確認:")
            print(f"[DEBUG] - ファイルセット名: {self.file_set.name}")
            print(f"[DEBUG] - extended_config keys: {list(extended_config.keys())}")
            print(f"[DEBUG] - sample_mode: {extended_config.get('sample_mode', 'None')}")
            print(f"[DEBUG] - sample_id: {extended_config.get('sample_id', 'None')}")
            print(f"[DEBUG] - sample_name: {extended_config.get('sample_name', 'None')}")
            
            # 試料情報
            sample_mode = extended_config.get('sample_mode', 'new')
            
            # 試料名・説明・組成情報
            sample_name = (extended_config.get('sample_name', '') or 
                          getattr(self.file_set, 'sample_name', '') or 
                          f"Sample_{self.file_set.name}")
            sample_description = (extended_config.get('sample_description', '') or 
                                getattr(self.file_set, 'sample_description', '') or 
                                "一括登録による試料")
            sample_composition = (extended_config.get('sample_composition', '') or 
                                getattr(self.file_set, 'sample_composition', '') or 
                                '')
            # 試料モード別処理
            print(f"[DEBUG] 試料モード判定: sample_mode={sample_mode}")
            
            if sample_mode == 'existing':
                # 既存試料ID を取得
                sample_id = extended_config.get('sample_id', None)
                print(f"[DEBUG] 既存試料モード - sample_id={sample_id}")
                
                if sample_id:
                    # 既存試料：sampleIdのみ設定（通常登録と同じ）
                    form_values.update({
                        'sampleId': sample_id,
                        # 参考値として試料情報も保持（通常登録と同じ構造）
                        'sampleNames': sample_name,  
                        'sampleDescription': sample_description,
                        'sampleComposition': sample_composition
                    })
                    print(f"[DEBUG] 既存試料設定完了: sample_id={sample_id}")
                else:
                    # 既存試料IDがない場合は新規作成にフォールバック
                    form_values.update({
                        'sampleNames': sample_name,
                        'sampleDescription': sample_description,
                        'sampleComposition': sample_composition
                    })
                    print(f"[WARNING] 既存試料モードですが試料IDがありません。新規作成に変更します。")
            else:
                # 新規作成モード：sampleNamesを設定（通常登録と同じ）
                form_values.update({
                    'sampleNames': sample_name,
                    'sampleDescription': sample_description,
                    'sampleComposition': sample_composition
                })
                print(f"[DEBUG] 新規作成モード設定完了: sample_name={sample_name}")
            
            # 試料名が設定されていない場合の補完
            if form_values.get('sampleMode') == 'new' and not form_values.get('sampleNames'):
                fallback_name = f"Sample_{self.file_set.name}"
                form_values['sampleNames'] = fallback_name
                print(f"[DEBUG] 試料名を補完: {fallback_name}")
            
            # 固有情報（カスタム値） - インボイススキーマ項目のみを抽出
            raw_custom_values = getattr(self.file_set, 'custom_values', {}) or {}
            
            # extended_configからもcustom_valuesを取得（フォールバック）
            extended_config = getattr(self.file_set, 'extended_config', {})
            if not raw_custom_values and extended_config.get('custom_values'):
                raw_custom_values = extended_config['custom_values']
                print(f"[DEBUG] extended_configからカスタム値を取得: {len(raw_custom_values)}個")
            elif not raw_custom_values:
                # extended_configから直接インボイススキーマ項目を抽出
                schema_fields = [
                    'accelerating_voltage', 'beam_species', 'gun_type', 'beam_energy',
                    'observation_method', 'major_processing_observation_conditions', 
                    'sample_temperature', 'remark', 'ion_species', 'electron_gun'
                ]
                for field in schema_fields:
                    if field in extended_config and extended_config[field]:
                        raw_custom_values[field] = extended_config[field]
                        print(f"[DEBUG] extended_configから直接取得: {field} = {extended_config[field]}")
            
            custom_values = {}
            
            # selected_datasetなどの内部用データを除外し、実際のインボイススキーマ項目のみを抽出
            excluded_keys = {
                'selected_dataset', 'dataset_id', 'dataset_name', 'dataset_info',
                'data_name', 'description', 'experiment_id', 'reference_url', 'tags',
                'sample_mode', 'sample_id', 'sample_name', 'sample_description', 
                'sample_composition', 'temp_folder', 'mapping_file', 'temp_created',
                'last_sample_id', 'last_sample_name', 'registration_timestamp'
            }
            for key, value in raw_custom_values.items():
                if key not in excluded_keys and value is not None and value != '':
                    custom_values[key] = value
            
            if custom_values:
                form_values['custom'] = custom_values
                print(f"[DEBUG] カスタム値設定: {len(custom_values)}個の項目")
                for key, value in list(custom_values.items())[:3]:  # 最初の3件のみログ出力
                    print(f"[DEBUG]   - {key}: {value}")
                if len(custom_values) > 3:
                    print(f"[DEBUG]   ... 他{len(custom_values) - 3}件")
            else:
                print(f"[DEBUG] カスタム値なし（除外後）")
                
            # 除外されたキーがあればログ出力
            excluded_items = {k: v for k, v in raw_custom_values.items() if k in excluded_keys}
            if excluded_items:
                print(f"[DEBUG] 除外されたカスタム項目: {list(excluded_items.keys())}")
            
            print(f"[DEBUG] フォーム値構築完了: dataName={form_values.get('dataName')}, sampleMode={form_values.get('sampleMode')}")
            return form_values
            
        except Exception as e:
            print(f"[ERROR] _build_form_values_from_fileset エラー: {e}")
            import traceback
            traceback.print_exc()
            return {
                'dataName': f"Error_Data_{getattr(self.file_set, 'name', 'unknown')}",
                'basicDescription': "フォーム値構築エラー",
                'sampleNames': f"Error_Sample_{getattr(self.file_set, 'name', 'unknown')}",
                'sampleDescription': "エラーによる試料"
            }
    
    def _build_files_payload(self, uploaded_files):
        """アップロード済みファイルからペイロードを構築（修正版：item_type属性を優先）"""
        try:
            print(f"[DEBUG] _build_files_payload開始 - ファイル数: {len(uploaded_files)}")
            
            dataFiles = {"data": []}
            attachments = []
            
            for file_item in uploaded_files:
                upload_id = getattr(file_item, 'upload_id', None)
                if not upload_id:
                    print(f"[WARNING] アップロードIDがないファイル: {file_item.name}")
                    continue
                
                file_name = file_item.name
                
                # ファイルの種類判定：item_type属性を優先使用
                item_type = getattr(file_item, 'item_type', None)
                
                if hasattr(file_item, 'item_type') and item_type:
                    # item_type属性が存在する場合はそれを使用
                    from classes.data_entry.core.file_set_manager import FileItemType
                    
                    if item_type == FileItemType.ATTACHMENT:
                        attachments.append({
                            "uploadId": upload_id,
                            "description": file_name
                        })
                        print(f"[DEBUG] 添付ファイル追加（item_type指定）: {file_name} -> {upload_id}")
                    else:
                        # DATA またはその他はデータファイル
                        dataFiles["data"].append({
                            "type": "upload", 
                            "id": upload_id
                        })
                        print(f"[DEBUG] データファイル追加（item_type指定）: {file_name} -> {upload_id}")
                        
                else:
                    # item_type属性がない場合は拡張子で判定（後方互換性）
                    file_ext = os.path.splitext(file_name)[1].lower()
                    
                    if file_ext in ['.xlsx', '.xls', '.pdf', '.doc', '.docx']:
                        attachments.append({
                            "uploadId": upload_id,
                            "description": file_name
                        })
                        print(f"[DEBUG] 添付ファイル追加（拡張子判定）: {file_name} -> {upload_id}")
                    else:
                        dataFiles["data"].append({
                            "type": "upload", 
                            "id": upload_id
                        })
                        print(f"[DEBUG] データファイル追加（拡張子判定）: {file_name} -> {upload_id}")
            
            print(f"[DEBUG] ペイロード構築完了 - データファイル: {len(dataFiles['data'])}個, 添付ファイル: {len(attachments)}個")
            return dataFiles, attachments
            
        except Exception as e:
            print(f"[ERROR] _build_files_payload エラー: {e}")
            import traceback
            traceback.print_exc()
            return {"data": []}, []
    
    def _execute_single_upload(self, bearer_token: str, dataset_id: str, file_item: FileItem) -> dict:
        """単一ファイルのアップロード処理（一括用）- Bearer Token自動選択対応"""
        try:
            if not os.path.exists(file_item.path):
                return {"error": f"ファイルが存在しません: {file_item.path}"}
            
            # 登録ファイル名を取得（重複回避のためフラット化されたファイル名を使用）
            register_filename = self._get_register_filename(file_item)
            file_size = os.path.getsize(file_item.path)
            encoded_filename = urllib.parse.quote(register_filename)
            
            print(f"[INFO] アップロード実行: {register_filename} (元ファイル: {os.path.basename(file_item.path)})")
            
            # APIエンドポイント
            url = f"https://rde-entry-api-arim.nims.go.jp/uploads?datasetId={dataset_id}"
            
            # リクエストヘッダー（Authorizationは削除、post_binary内で自動選択）
            headers = {
                "Accept": "application/json",
                "X-File-Name": encoded_filename,
                "User-Agent": "PythonUploader/1.0"
            }
            
            print(f"[DEBUG] URL: {url}")
            print(f"[DEBUG] X-File-Name: {encoded_filename}")
            
            # バイナリデータ読み込み
            with open(file_item.path, 'rb') as f:
                binary_data = f.read()
            
            # Bearer Token自動選択対応のpost_binaryを使用
            from classes.utils.api_request_helper import post_binary
            
            print(f"[DEBUG] API呼び出し開始: POST {url}")
            print(f"[DEBUG] バイナリデータサイズ: {len(binary_data)} bytes")
            
            resp = post_binary(url, data=binary_data, bearer_token=None, headers=headers)
            if resp is None:
                print(f"[ERROR] API呼び出し失敗: レスポンスがNone")
                return {"error": "API呼び出し失敗: レスポンスがありません"}
            
            print(f"[DEBUG] レスポンス受信: ステータスコード {resp.status_code}")
            print(f"[DEBUG] レスポンスヘッダー: {dict(resp.headers)}")
            
            # ステータスコードチェック（200番台は成功）
            if not (200 <= resp.status_code < 300):
                error_text = resp.text[:500] if hasattr(resp, 'text') else 'レスポンステキストなし'
                print(f"[ERROR] HTTPエラー: {resp.status_code}")
                print(f"[ERROR] レスポンス内容: {error_text}")
                return {"error": f"HTTP {resp.status_code}: {error_text}"}
            
            print(f"[SUCCESS] HTTPレスポンス成功: {resp.status_code}")
            
            # JSONレスポンスをパース
            try:
                data = resp.json()
                print(f"[DEBUG] JSONパース成功: {len(str(data))} 文字")
                print(f"[DEBUG] レスポンス構造: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            except Exception as json_error:
                print(f"[ERROR] JSONパースエラー: {json_error}")
                print(f"[ERROR] レスポンステキスト: {resp.text[:200]}")
                return {"error": f"JSONパースエラー: {json_error}"}
            
            # uploadIdを抽出
            upload_id = data.get("uploadId")
            if not upload_id:
                print(f"[ERROR] uploadIdがレスポンスに含まれていません")
                print(f"[ERROR] レスポンス内容: {data}")
                return {"error": "レスポンスにuploadIdが含まれていません", "response_data": data}
            
            print(f"[SUCCESS] アップロード成功: {register_filename} -> uploadId = {upload_id}")
            
            # レスポンス保存
            from config.common import OUTPUT_RDE_DIR
            output_dir = os.path.join(OUTPUT_RDE_DIR, "data")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"upload_response_{upload_id}.json")
            with open(output_path, "w", encoding="utf-8") as outf:
                json.dump(data, outf, ensure_ascii=False, indent=2)
            
            return {
                "upload_id": upload_id,
                "response_data": data,
                "filename": register_filename
            }
            
        except Exception as e:
            print(f"[ERROR] 単一ファイルアップロードエラー: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def _execute_batch_upload(self) -> bool:
        """ファイル一括アップロードを実行（Bearer Token自動選択対応）"""
        try:
            print("[INFO] ファイル一括アップロード開始")
            
            # 注意: Bearer Tokenは不要（API呼び出し時に自動選択される）
            
            # データセットIDを取得
            dataset_id = getattr(self.file_set, 'dataset_id', None)
            if not dataset_id:
                dataset_info = getattr(self.file_set, 'dataset_info', None)
                if dataset_info and dataset_info.get('id'):
                    dataset_id = dataset_info['id']
                else:
                    extended_config = getattr(self.file_set, 'extended_config', {})
                    dataset_id = extended_config.get('dataset_id')
            
            if not dataset_id:
                print("[ERROR] データセットIDが取得できません")
                QMessageBox.warning(self, "エラー", "データセット情報が設定されていません。")
                return False
            
            # 対象ファイル取得（path_mapping.xlsxは_get_display_file_items内で処理済み）
            valid_items = self.file_set.get_valid_items()
            file_items = [item for item in valid_items if item.file_type == FileType.FILE]
            display_items = self._get_display_file_items(file_items)
            
            # path_mapping.xlsxは既に_get_display_file_itemsで追加されているため、ここでは追加しない
            print(f"[DEBUG] アップロード処理: 対象ファイル数 = {len(display_items)}")
            
            if not display_items:
                QMessageBox.warning(self, "エラー", "アップロード対象のファイルがありません。")
                return False
            
            # プログレスダイアログ
            total_files = len(display_items)
            progress = QProgressDialog("ファイルアップロード中...", "キャンセル", 0, total_files, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            
            upload_success_count = 0
            upload_failed_count = 0
            
            for i, file_item in enumerate(display_items):
                if progress.wasCanceled():
                    print("[INFO] ユーザーによりアップロードがキャンセルされました")
                    progress.close()
                    return False
                
                progress.setLabelText(f"アップロード中: {file_item.name} ({i+1}/{total_files})")
                progress.setValue(i)
                QApplication.processEvents()
                
                try:
                    # 単一ファイルアップロード実行（bearer_tokenは不要、自動選択される）
                    upload_result = self._execute_single_upload(None, dataset_id, file_item)
                    
                    if upload_result and upload_result.get('upload_id'):
                        upload_id = upload_result['upload_id']
                        setattr(file_item, 'upload_id', upload_id)
                        setattr(file_item, 'upload_response', upload_result.get('response_data', {}))
                        upload_success_count += 1
                        print(f"[SUCCESS] {file_item.name} -> アップロードID: {upload_id}")
                    else:
                        upload_failed_count += 1
                        error_detail = upload_result.get('error', '不明なエラー') if upload_result else 'レスポンスなし'
                        print(f"[ERROR] {file_item.name} -> {error_detail}")
                        
                except Exception as e:
                    upload_failed_count += 1
                    print(f"[ERROR] {file_item.name} -> 例外: {str(e)}")
            
            progress.setValue(total_files)
            progress.close()
            
            # 結果表示
            print(f"[INFO] アップロード完了 - 成功: {upload_success_count}件, 失敗: {upload_failed_count}件")
            
            # アップロード済みファイル情報をファイルセットに保存（データ登録で再利用するため）
            if upload_success_count > 0:
                uploaded_items = [item for item in display_items if hasattr(item, 'upload_id') and item.upload_id]
                setattr(self.file_set, '_uploaded_items', uploaded_items)
                print(f"[DEBUG] アップロード済みアイテムをファイルセットに保存: {len(uploaded_items)}個")
            
            if upload_failed_count == 0:
                QMessageBox.information(self, "完了", f"全{total_files}ファイルのアップロードが完了しました。")
                return True
            elif upload_success_count > 0:
                reply = QMessageBox.question(
                    self, "一部失敗", 
                    f"アップロード結果:\n成功: {upload_success_count}件\n失敗: {upload_failed_count}件\n\n続行しますか？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                return reply == QMessageBox.Yes
            else:
                QMessageBox.warning(self, "失敗", "全てのファイルアップロードに失敗しました。")
                return False
                
        except Exception as e:
            print(f"[ERROR] 一括アップロード処理エラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"一括アップロード処理でエラーが発生しました:\n{str(e)}")
            return False
    
    def _execute_single_upload_internal(self, bearer_token: str, dataset_id: str, file_item: FileItem) -> dict:
        """単一ファイルのアップロード実行 - Bearer Token自動選択対応"""
        try:
            # ファイルパスの決定（複数の属性をチェック）
            file_path = getattr(file_item, 'absolute_path', None)
            if not file_path:
                file_path = getattr(file_item, 'path', None)
            if not file_path:
                file_path = file_item.name  # 最後の手段
            
            if not os.path.exists(file_path):
                return {'success': False, 'error': f'ファイルが存在しません: {file_path}'}
            
            # アップロードAPI呼び出し
            url = f"https://rde-entry-api-arim.nims.go.jp/uploads?datasetId={dataset_id}"
            
            # ファイル読み込み
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # ヘッダー設定（Authorizationは削除、post_binary内で自動選択）
            filename = os.path.basename(file_path)
            encoded_filename = urllib.parse.quote(filename)
            headers = {
                "Accept": "application/json",
                "X-File-Name": encoded_filename,
                "User-Agent": "PythonUploader/1.0"
            }
            
            # Bearer Token自動選択対応のpost_binaryを使用
            from classes.utils.api_request_helper import post_binary
            resp = post_binary(url, data=file_data, bearer_token=None, headers=headers)
            
            if resp is None:
                return {'success': False, 'error': 'API呼び出し失敗: レスポンスがありません'}
            
            if not (200 <= resp.status_code < 300):
                error_text = resp.text[:500] if hasattr(resp, 'text') else 'レスポンステキストなし'
                return {'success': False, 'error': f'HTTP {resp.status_code}: {error_text}'}
            
            # レスポンス解析
            try:
                response_data = resp.json()
                if 'data' in response_data and 'id' in response_data['data']:
                    upload_id = response_data['data']['id']
                    return {
                        'success': True,
                        'upload_id': upload_id,
                        'response_data': response_data
                    }
                else:
                    return {'success': False, 'error': 'アップロードIDが取得できません'}
            except Exception as json_error:
                return {'success': False, 'error': f'JSON解析エラー: {str(json_error)}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _execute_data_registration(self) -> bool:
        """データ登録を実行（Bearer Token自動選択対応）"""
        try:
            print("[INFO] データ登録実行開始")
            
            # 注意: Bearer Tokenは不要（entry_data関数内で自動選択される）
            
            # データセット情報取得
            dataset_info = getattr(self.file_set, 'dataset_info', None)
            if not dataset_info:
                print("[ERROR] データセット情報が取得できません")
                QMessageBox.warning(self, "エラー", "データセット情報が設定されていません。")
                return False
            
            dataset_id = dataset_info.get('id')
            if not dataset_id:
                print("[ERROR] データセットIDが取得できません")
                return False
            
            # アップロード済みファイルを取得（保存されたアイテムを優先使用）
            if hasattr(self.file_set, '_uploaded_items') and self.file_set._uploaded_items:
                display_items = self.file_set._uploaded_items
                print(f"[DEBUG] データ登録処理: 保存されたアップロード済みアイテムを使用 - {len(display_items)}個")
            else:
                # フォールバック: 新規に取得（アップロードIDは失われている可能性あり）
                valid_items = self.file_set.get_valid_items()
                file_items = [item for item in valid_items if item.file_type == FileType.FILE]
                display_items = self._get_display_file_items(file_items)
                print(f"[DEBUG] データ登録処理: 新規取得（フォールバック） - {len(display_items)}個")
            
            # アップロードIDが設定されているファイルのみ対象
            uploaded_files = [item for item in display_items if hasattr(item, 'upload_id') and item.upload_id]
            if not uploaded_files:
                QMessageBox.warning(self, "エラー", "アップロード済みファイルがありません。\n先にファイルアップロードを実行してください。")
                return False

            print(f"[INFO] データ登録対象ファイル数: {len(uploaded_files)}")
            print("[DEBUG] uploaded_files 内容:")
            for item in uploaded_files:
                print(f"  - name: {getattr(item, 'name', None)}, item_type: {getattr(item, 'item_type', None)}, upload_id: {getattr(item, 'upload_id', None)}")

            # フォーム値を構築
            form_values = self._build_form_values_from_fileset()
            if not form_values:
                QMessageBox.warning(self, "エラー", "フォーム値の構築に失敗しました。")
                return False

            # ファイルペイロードを構築
            dataFiles, attachments = self._build_files_payload(uploaded_files)

            print(f"[DEBUG] attachments 構築直後の内容: {attachments}")

            if not dataFiles.get('data') and not attachments:
                print("[ERROR] データファイルまたは添付ファイルが必要です")
                return False

            # ペイロードプレビュー表示
            if not self._show_payload_confirmation(dataset_info, form_values, dataFiles, attachments):
                return False  # ユーザーがキャンセルした場合

            print(f"[DEBUG] データ登録開始:")
            print(f"  - データセット: {dataset_info}")
            print(f"  - フォーム値: {form_values}")
            print(f"  - データファイル数: {len(dataFiles.get('data', []))}")
            print(f"  - 添付ファイル数: {len(attachments)}")
            
            # プログレスダイアログ
            progress = QProgressDialog("データ登録中...", None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            
            try:
                # 通常登録タブと同じentry_data関数を使用（bearer_token=Noneで自動選択）
                from ..core.data_register_logic import entry_data
                
                result = entry_data(
                    bearer_token=None,
                    dataFiles=dataFiles,
                    attachements=attachments,
                    dataset_info=dataset_info,
                    form_values=form_values,
                    progress=progress
                )
                
                progress.close()
                
                if result and not result.get('error'):
                    # 成功処理
                    print("[SUCCESS] データ登録完了")
                    
                    # 試料ID保存
                    sample_info = self._extract_sample_info_from_response(result)
                    if sample_info:
                        self._save_sample_info_to_fileset(sample_info)
                    
                    return True
                else:
                    # エラー処理
                    error_detail = result.get('detail', '不明なエラー') if result else 'レスポンスなし'
                    print(f"[ERROR] データ登録エラー: {error_detail}")
                    return False
                
            except Exception as e:
                progress.close()
                print(f"[ERROR] entry_data呼び出しエラー: {e}")
                return False
                
        except Exception as e:
            print(f"[ERROR] データ登録処理エラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"データ登録処理でエラーが発生しました:\n{str(e)}")
            return False

    def _extract_sample_info_from_response(self, response_data: dict) -> Optional[dict]:
        """APIレスポンスから試料情報を抽出"""
        try:
            print(f"[DEBUG] _extract_sample_info_from_response開始")
            print(f"[DEBUG] レスポンスデータ構造: {type(response_data)}")
            
            if not response_data or not isinstance(response_data, dict):
                print(f"[WARNING] レスポンスデータが無効: {response_data}")
                return None
                
            # レスポンス構造の確認：通常形式 vs wrapped形式
            data = None
            if 'data' in response_data:
                data = response_data['data']
            elif 'response' in response_data and response_data.get('response', {}).get('data'):
                # wrapped形式（success/responseで包まれている）
                data = response_data['response']['data']
                print(f"[DEBUG] wrapped形式のレスポンスを検出")
            
            if not data:
                print(f"[WARNING] レスポンスに'data'フィールドがありません")
                print(f"[DEBUG] レスポンス構造: {list(response_data.keys())}")
                return None
                
            print(f"[DEBUG] data構造: {data}")
            
            # relationshipsから試料情報を取得
            relationships = data.get('relationships', {})
            sample_rel = relationships.get('sample', {})
            sample_data = sample_rel.get('data', {})
            sample_id = sample_data.get('id')
            
            if sample_id:
                sample_info = {
                    'sample_id': sample_id,
                    'sample_name': f'Sample (ID: {sample_id[:8]}...)',
                    'mode': 'existing'
                }
                print(f"[DEBUG] 試料情報抽出成功: {sample_info}")
                return sample_info
            else:
                print(f"[WARNING] レスポンスから試料IDを抽出できませんでした")
                return None
            
        except Exception as e:
            print(f"[ERROR] 試料情報抽出エラー: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _save_sample_info_to_fileset(self, sample_info: dict):
        """試料情報をファイルセットに保存"""
        try:
            print(f"[DEBUG] 試料情報をファイルセットに保存: {sample_info}")
            
            if not sample_info or not hasattr(self, 'file_set'):
                print("[WARNING] 試料情報またはファイルセットが無効です")
                return
            
            # extended_configに試料情報を保存
            if not hasattr(self.file_set, 'extended_config') or not self.file_set.extended_config:
                self.file_set.extended_config = {}
            
            # 試料情報の保存
            if 'sample_id' in sample_info:
                self.file_set.extended_config['sample_id'] = sample_info['sample_id']
                self.file_set.extended_config['sample_mode'] = 'existing'
                print(f"[DEBUG] 既存試料ID保存: {sample_info['sample_id']}")
            
            if 'sample_name' in sample_info:
                self.file_set.extended_config['sample_name'] = sample_info['sample_name']
            
            # 登録タイムスタンプ
            from datetime import datetime
            self.file_set.extended_config['registration_timestamp'] = datetime.now().isoformat()
            
            print(f"[DEBUG] ファイルセットへの試料情報保存完了")
            
        except Exception as e:
            print(f"[ERROR] 試料情報保存エラー: {e}")
            import traceback
            traceback.print_exc()
    
    def _show_payload_confirmation(self, dataset_info, form_values, dataFiles, attachments):
        """ペイロード確認ダイアログを表示
        
        Args:
            dataset_info: データセット情報
            form_values: フォーム値
            dataFiles: データファイル情報
            attachments: 添付ファイル情報
            
        Returns:
            bool: 実行を続行するかどうか
        """
        import json
        
        # ペイロードを構築（表示用）
        payload = {
            'data': {
                'type': 'entry',
                'attributes': {
                    'invoice': {
                        'datasetId': dataset_info.get('id', ''),
                        'basic': {
                            'dataOwnerId': form_values.get('dataOwnerId', ''),
                            'dataName': form_values.get('dataName', ''),
                            'instrumentId': form_values.get('instrumentId', ''),
                            'description': form_values.get('basicDescription', ''),
                            'experimentId': form_values.get('experimentId', '')
                        },
                        'custom': form_values.get('custom', {}),
                        'sample': {}
                    }
                },
                'relationships': {
                    'dataFiles': dataFiles
                }
            },
            'meta': {
                'attachments': attachments
            }
        }
        
        # 試料情報を追加（通常登録と同じ構造）
        if form_values.get('sampleId'):
            # 既存試料の場合：sampleIdのみ設定
            payload['data']['attributes']['invoice']['sample'] = {
                'sampleId': form_values.get('sampleId')
            }
        elif form_values.get('sampleNames'):
            # 新規作成の場合：詳細情報を設定
            payload['data']['attributes']['invoice']['sample'] = {
                'description': form_values.get('sampleDescription', ''),
                'composition': form_values.get('sampleComposition', ''),
                'referenceUrl': form_values.get('referenceUrl', ''),
                'hideOwner': None,
                'names': [form_values.get('sampleNames', '')],
                'relatedSamples': [],
                'tags': None,
                'generalAttributes': None,
                'specificAttributes': None,
                'ownerId': form_values.get('dataOwnerId', '')
            }
        
        # JSONを整形
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
        
        # 切り詰め版を作成（1000文字まで）
        payload_preview = payload_json[:1000] + "..." if len(payload_json) > 1000 else payload_json
        
        # 確認ダイアログ作成
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QFont
        
        dialog = QDialog(self)
        dialog.setWindowTitle("データ登録ペイロード確認")
        dialog.setMinimumSize(800, 600)
        dialog.setModal(True)
        
        layout = QVBoxLayout(dialog)
        
        # 説明ラベル
        info_label = QLabel("以下の内容でデータ登録を実行します：")
        layout.addWidget(info_label)
        
        # ペイロード表示エリア
        payload_text = QTextEdit()
        payload_text.setFont(QFont("Consolas", 9))
        payload_text.setPlainText(payload_preview)
        payload_text.setReadOnly(True)
        layout.addWidget(payload_text)
        
        # 全文表示ボタンと実行ボタンのレイアウト
        button_layout = QHBoxLayout()
        
        # 全文表示ボタン
        full_text_btn = QPushButton("全文表示")
        full_text_btn.clicked.connect(lambda: self._show_full_payload(payload_json))
        button_layout.addWidget(full_text_btn)
        
        button_layout.addStretch()
        
        # 実行・キャンセルボタン
        execute_btn = QPushButton("データ登録実行")
        execute_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        cancel_btn = QPushButton("キャンセル")
        
        execute_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        
        button_layout.addWidget(execute_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        return dialog.exec_() == QDialog.Accepted
    
    def _show_full_payload(self, payload_json):
        """ペイロード全文表示ダイアログ
        
        Args:
            payload_json: 完全なJSONペイロード文字列
        """
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QPushButton, QTextEdit
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QFont
        
        dialog = QDialog(self)
        dialog.setWindowTitle("データ登録ペイロード（全文）")
        dialog.setMinimumSize(1000, 700)
        dialog.setModal(True)
        
        layout = QVBoxLayout(dialog)
        
        # テキストエリア
        text_area = QTextEdit()
        text_area.setFont(QFont("Consolas", 9))
        text_area.setPlainText(payload_json)
        text_area.setReadOnly(True)
        layout.addWidget(text_area)
        
        # 閉じるボタン
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec_()
    
    def _get_register_filename(self, file_item: FileItem) -> str:
        """FileSetPreviewWidget用：登録時のファイル名を取得（単一ファイルセット対応）"""
        try:
            # 単一ファイルセット（self.file_set）を使用
            organize_method = getattr(self.file_set, 'organize_method', None)
            if organize_method == PathOrganizeMethod.FLATTEN:
                # フラット化の場合は、相対パスをダブルアンダースコアで置き換え
                relative_path = file_item.relative_path.replace('/', '__').replace('\\', '__')
                return relative_path
            elif organize_method == PathOrganizeMethod.ZIP:
                # ZIP化の場合の表示処理
                return self._get_zip_display_filename_for_single_fileset(file_item)
            else:
                return file_item.relative_path
        except Exception as e:
            print(f"[DEBUG] FileSetPreviewWidget._get_register_filename エラー: {e}")
            return file_item.name or "不明なファイル"
    
    def _get_zip_display_filename_for_single_fileset(self, file_item: FileItem) -> str:
        """単一ファイルセット用のZIP化表示ファイル名取得"""
        try:
            relative_path = Path(file_item.relative_path)
            
            # フォルダのZIP化判定
            if self._is_file_zipped_for_single_fileset(file_item):
                # ZIP化されるファイル：ZIPファイル名のみ表示
                if len(relative_path.parts) == 1:
                    # ルート直下のファイル：個別ZIP化
                    return f"{file_item.name}.zip"
                else:
                    # フォルダ内ファイル：フォルダがZIP化される
                    return f"{relative_path.parts[0]}.zip"
            else:
                # ZIP化されないファイル：元ファイル名
                return file_item.name
        except Exception as e:
            print(f"[ERROR] 単一ファイルセットZIP表示ファイル名取得エラー: {e}")
            return file_item.name or "不明なファイル"
    
    def _is_file_zipped_for_single_fileset(self, file_item: FileItem) -> bool:
        """単一ファイルセット用のZIP化判定"""
        try:
            # 元からのZIPファイルかチェック
            if file_item.extension and file_item.extension.lower() == '.zip':
                # ベースディレクトリに最初から格納されているZIPファイル
                return False  # そのまま表示
            
            # ZIP化対象ディレクトリを特定
            all_items = self.file_set.get_valid_items()
            zip_directories = set()
            for item in all_items:
                if item.file_type == FileType.DIRECTORY and getattr(item, 'is_zip', False):
                    zip_directories.add(item.relative_path)
            
            # ファイルがZIP化対象ディレクトリに含まれているかチェック
            relative_path = file_item.relative_path
            for zip_dir in zip_directories:
                if relative_path.startswith(zip_dir + '/') or relative_path.startswith(zip_dir + '\\'):
                    return True
            
            return False
            
        except Exception as e:
            print(f"[ERROR] 単一ファイルセットZIP化判定エラー: {e}")
            return False


class BatchRegisterPreviewDialog(QDialog):
    """一括登録プレビューダイアログ"""
    
    def __init__(self, file_sets: List[FileSet], parent=None, bearer_token: str = None):
        super().__init__(parent)
        self.file_sets = file_sets
        self.duplicate_files = set()
        self.bearer_token = bearer_token
        self.setWindowTitle("一括登録プレビュー")
        self.setModal(True)
        
        # ダイアログサイズをディスプレイの90%に設定
        self.setup_dialog_size()
        
        self.setup_ui()
        self.check_duplicates()
        self.load_data()
    
    def setup_dialog_size(self):
        """ダイアログサイズを設定（ディスプレイ高さの90%）"""
        try:
            from PyQt5.QtWidgets import QDesktopWidget
            desktop = QDesktopWidget()
            screen_rect = desktop.screenGeometry()
            
            # ディスプレイサイズの90%に設定
            target_width = int(screen_rect.width() * 0.9)
            target_height = int(screen_rect.height() * 0.9)
            
            # 最小サイズを設定
            min_width = 800
            min_height = 600
            target_width = max(target_width, min_width)
            target_height = max(target_height, min_height)
            
            self.resize(target_width, target_height)
            
            # ダイアログを画面中央に配置
            self.move(
                (screen_rect.width() - target_width) // 2,
                (screen_rect.height() - target_height) // 2
            )
            
            print(f"[DEBUG] プレビューダイアログサイズ設定: {target_width}x{target_height}")
        except Exception as e:
            print(f"[WARNING] ダイアログサイズ設定エラー: {e}")
            self.resize(1000, 700)  # フォールバック
        
        self.setup_ui()
        self.check_duplicates()
        self.load_data()
    
    def setup_ui(self):
        """UIセットアップ"""
        layout = QVBoxLayout()
        
        # 上部: サマリー情報
        summary_label = QLabel()
        summary_label.setFont(QFont("", 10, QFont.Bold))
        self.summary_label = summary_label
        layout.addWidget(summary_label)
        
        # 中央: ファイルセットタブ
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget, 1)
        
        # 下部: ボタン
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def check_duplicates(self):
        """ファイル重複をチェック"""
        file_paths = {}  # path -> [file_set_names]
        
        try:
            for file_set in self.file_sets:
                if not file_set:
                    continue
                    
                valid_items = file_set.get_valid_items()
                for item in valid_items:
                    if item.file_type == FileType.FILE and item.path:
                        if item.path not in file_paths:
                            file_paths[item.path] = []
                        file_paths[item.path].append(file_set.name)
            
            # 重複ファイルを特定
            for path, file_set_names in file_paths.items():
                if len(file_set_names) > 1:
                    self.duplicate_files.add(path)
                    # 重複ファイルを除外フラグを設定
                    for file_set in self.file_sets:
                        if not file_set:
                            continue
                        for item in file_set.items:
                            if hasattr(item, 'path') and item.path == path:
                                item.is_excluded = True
                                
        except Exception as e:
            print(f"重複チェック中にエラー: {e}")
    
    def load_data(self):
        """データを読み込み"""
        try:
            # サマリー情報
            total_filesets = len(self.file_sets)
            
            if total_filesets == 0:
                self.summary_label.setText("ファイルセットがありません")
                return
            
            total_files = 0
            total_size = 0
            
            for fs in self.file_sets:
                if fs:
                    try:
                        valid_items = [item for item in fs.get_valid_items() if item.file_type == FileType.FILE]
                        total_files += len(valid_items)
                        total_size += fs.get_total_size()
                    except Exception as e:
                        print(f"ファイルセット '{fs.name}' の統計取得中にエラー: {e}")
            
            duplicate_count = len(self.duplicate_files)
            
            summary_text = f"ファイルセット数: {total_filesets}個 | ファイル数: {total_files}個 | "
            summary_text += f"総サイズ: {self._format_size(total_size)}"
            
            if duplicate_count > 0:
                summary_text += f" | <font color='red'>重複ファイル: {duplicate_count}個</font>"
            
            self.summary_label.setText(summary_text)
            
            # ファイルセットタブを作成
            for i, file_set in enumerate(self.file_sets):
                if not file_set:
                    continue
                    
                try:
                    preview_widget = FileSetPreviewWidget(file_set, self.duplicate_files, self.bearer_token)
                    tab_name = file_set.name or f"ファイルセット{i+1}"
                    
                    # 重複ファイルがある場合は警告アイコンを追加
                    has_duplicates = False
                    for item in (file_set.items or []):
                        if hasattr(item, 'path') and item.path in self.duplicate_files:
                            has_duplicates = True
                            break
                    
                    if has_duplicates:
                        tab_name += " ⚠"  # 重複アイコン
                    
                    self.tab_widget.addTab(preview_widget, tab_name)
                except Exception as e:
                    print(f"ファイルセット '{file_set.name}' のタブ作成中にエラー: {e}")
                    # エラーが発生したファイルセットのタブには簡易メッセージを表示
                    error_widget = QLabel(f"エラー: {str(e)}")
                    self.tab_widget.addTab(error_widget, f"{file_set.name or 'エラー'} ❌")
                    
        except Exception as e:
            print(f"プレビューデータ読み込み中にエラー: {e}")
            self.summary_label.setText(f"エラー: {str(e)}")
    
    def _batch_upload_files(self):
        """ファイル一括アップロード処理（Bearer Token自動選択対応）"""
        try:
            print("[INFO] ファイル一括アップロード開始")
            
            # 注意: Bearer Tokenは不要（API呼び出し時に自動選択される）
            
            # 現在表示中のファイルセットを取得
            if not hasattr(self, 'file_set') or not self.file_set:
                QMessageBox.warning(self, "エラー", "ファイルセットが選択されていません。")
                return
            
            # データセットIDを取得
            dataset_info = getattr(self.file_set, 'dataset_info', None)
            dataset_id = None
            if dataset_info and isinstance(dataset_info, dict):
                dataset_id = dataset_info.get('id')
            
            if not dataset_id:
                QMessageBox.warning(self, "エラー", "データセットIDが取得できません。")
                return
            
            # 含まれるファイル一覧を取得
            valid_items = self.file_set.get_valid_items()
            file_items = [item for item in valid_items if item.file_type == FileType.FILE]
            
            # ZIP化されたファイルを表示用にフィルタリング
            display_items = self._get_display_file_items(file_items)
            
            if not display_items:
                QMessageBox.information(self, "情報", "アップロードするファイルがありません。")
                return
            
            # マッピングファイルがある場合は追加
            mapping_file_path = self._get_mapping_file_path()
            mapping_item = None
            if mapping_file_path and os.path.exists(mapping_file_path):
                mapping_item = FileItem(
                    path=mapping_file_path,
                    relative_path="path_mapping.xlsx",
                    name="path_mapping.xlsx",
                    file_type=FileType.FILE
                )
                display_items.append(mapping_item)
                print(f"[INFO] マッピングファイルも追加: {mapping_file_path}")
            
            total_files = len(display_items)
            print(f"[INFO] 一括アップロード対象ファイル数: {total_files}個")
            
            # プログレスダイアログ
            progress = QProgressDialog("ファイル一括アップロード中...", "キャンセル", 0, total_files, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            
            # アップロード結果を保存
            upload_results = []
            failed_files = []
            
            for i, file_item in enumerate(display_items):
                if progress.wasCanceled():
                    print("[INFO] ユーザーによりアップロードがキャンセルされました")
                    break
                
                progress.setLabelText(f"アップロード中: {file_item.name} ({i+1}/{total_files})")
                progress.setValue(i)
                QApplication.processEvents()
                
                try:
                    # 個別アップロード処理を呼び出し（bearer_tokenは不要、自動選択される）
                    upload_result = self._execute_single_upload(None, dataset_id, file_item)
                    
                    if upload_result and upload_result.get('upload_id'):
                        upload_id = upload_result['upload_id']
                        setattr(file_item, 'upload_id', upload_id)
                        setattr(file_item, 'upload_response', upload_result.get('response_data', {}))
                        upload_results.append(upload_result)
                        print(f"[SUCCESS] {file_item.name} -> ID: {upload_id}")
                    else:
                        error_detail = upload_result.get('error', '不明なエラー') if upload_result else 'レスポンスなし'
                        failed_files.append((file_item.name, error_detail))
                        print(f"[ERROR] {file_item.name} -> {error_detail}")
                        
                except Exception as e:
                    error_msg = str(e)
                    failed_files.append((file_item.name, error_msg))
                    print(f"[ERROR] {file_item.name} -> 例外: {error_msg}")
            
            progress.setValue(total_files)
            progress.close()
            
            # 結果表示
            success_count = len(upload_results)
            failed_count = len(failed_files)
            
            result_message = f"""ファイル一括アップロード完了

成功: {success_count}個
失敗: {failed_count}個
総計: {total_files}個"""
            
            if failed_files:
                result_message += "\n\n失敗したファイル:\n"
                for name, error in failed_files[:5]:  # 最初の5件まで表示
                    result_message += f"- {name}: {error}\n"
                if len(failed_files) > 5:
                    result_message += f"... 他{len(failed_files) - 5}件"
            
            if failed_count == 0:
                QMessageBox.information(self, "アップロード完了", result_message)
            else:
                QMessageBox.warning(self, "アップロード完了（一部失敗）", result_message)
            
            print(f"[INFO] 一括アップロード完了: 成功={success_count}, 失敗={failed_count}")
            
        except Exception as e:
            print(f"[ERROR] 一括アップロード処理エラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"一括アップロード処理でエラーが発生しました:\n{str(e)}")
    
    def _execute_single_upload(self, bearer_token: str, dataset_id: str, file_item: FileItem) -> dict:
        """単一ファイルのアップロード処理（一括用）- 個別アップロード処理と同じ方法"""
        try:
            if not os.path.exists(file_item.path):
                return {"error": f"ファイルが存在しません: {file_item.path}"}
            
            # 登録ファイル名を取得（重複回避のためフラット化されたファイル名を使用） 
            register_filename = self._get_register_filename(file_item)
            file_size = os.path.getsize(file_item.path)
            encoded_filename = urllib.parse.quote(register_filename)
            
            print(f"[INFO] アップロード実行: {register_filename} (元ファイル: {os.path.basename(file_item.path)})")
            
            # APIエンドポイント
            url = f"https://rde-entry-api-arim.nims.go.jp/uploads?datasetId={dataset_id}"
            
            # リクエストヘッダー（Authorizationは削除、post_binary内で自動選択）
            headers = {
                "Accept": "application/json",
                "X-File-Name": encoded_filename,
                "User-Agent": "PythonUploader/1.0"
            }
            
            print(f"[DEBUG] URL: {url}")
            print(f"[DEBUG] X-File-Name: {encoded_filename}")
            
            # バイナリデータ読み込み
            with open(file_item.path, 'rb') as f:
                binary_data = f.read()
            
            # Bearer Token自動選択対応のpost_binaryを使用
            from classes.utils.api_request_helper import post_binary
            
            print(f"[DEBUG] API呼び出し開始: POST {url}")
            print(f"[DEBUG] バイナリデータサイズ: {len(binary_data)} bytes")
            
            resp = post_binary(url, data=binary_data, bearer_token=None, headers=headers)
            if resp is None:
                print(f"[ERROR] API呼び出し失敗: レスポンスがNone")
                return {"error": "API呼び出し失敗: レスポンスがありません"}
            
            print(f"[DEBUG] レスポンス受信: ステータスコード {resp.status_code}")
            print(f"[DEBUG] レスポンスヘッダー: {dict(resp.headers)}")
            
            # ステータスコードチェック（200番台は成功）
            if not (200 <= resp.status_code < 300):
                error_text = resp.text[:500] if hasattr(resp, 'text') else 'レスポンステキストなし'
                print(f"[ERROR] HTTPエラー: {resp.status_code}")
                print(f"[ERROR] レスポンス内容: {error_text}")
                return {"error": f"HTTP {resp.status_code}: {error_text}"}
            
            print(f"[SUCCESS] HTTPレスポンス成功: {resp.status_code}")
            
            # JSONレスポンスをパース
            try:
                data = resp.json()
                print(f"[DEBUG] JSONパース成功: {len(str(data))} 文字")
                print(f"[DEBUG] レスポンス構造: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            except Exception as json_error:
                print(f"[ERROR] JSONパースエラー: {json_error}")
                print(f"[ERROR] レスポンステキスト: {resp.text[:200]}")
                return {"error": f"JSONパースエラー: {json_error}"}
            
            # uploadIdを抽出
            upload_id = data.get("uploadId")
            if not upload_id:
                print(f"[ERROR] uploadIdがレスポンスに含まれていません")
                print(f"[ERROR] レスポンス内容: {data}")
                return {"error": "レスポンスにuploadIdが含まれていません", "response_data": data}
            
            print(f"[SUCCESS] アップロード成功: {register_filename} -> uploadId = {upload_id}")
            
            # レスポンス保存
            from config.common import OUTPUT_RDE_DIR
            output_dir = os.path.join(OUTPUT_RDE_DIR, "data")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"upload_response_{upload_id}.json")
            with open(output_path, "w", encoding="utf-8") as outf:
                json.dump(data, outf, ensure_ascii=False, indent=2)
            
            return {
                "upload_id": upload_id,
                "response_data": data,
                "filename": register_filename
            }
            
        except Exception as e:
            print(f"[ERROR] 単一ファイルアップロードエラー: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}
    
    def _get_mapping_file_path(self) -> Optional[str]:
        """マッピングファイルのパスを取得"""
        try:
            # 一時フォルダパスを取得
            temp_folder = getattr(self.file_set, 'temp_folder', None)
            extended_config = getattr(self.file_set, 'extended_config', {})
            if not temp_folder and 'temp_folder' in extended_config:
                temp_folder = extended_config['temp_folder']
            
            if temp_folder and os.path.exists(temp_folder):
                mapping_path = os.path.join(temp_folder, "path_mapping.xlsx")
                if os.path.exists(mapping_path):
                    return mapping_path
            
            return None
        except Exception as e:
            print(f"[WARNING] マッピングファイル取得エラー: {e}")
            return None
    
    def _batch_register_data(self):
        """データ登録処理（一括アップロード + データ登録）"""
        try:
            print("[INFO] データ登録処理開始")
            
            # 前提条件チェック
            if not self._validate_registration_prerequisites():
                return
            
            # 確認ダイアログ
            reply = QMessageBox.question(
                self, "データ登録確認", 
                "データ登録を実行しますか？\n\n"
                "この処理では以下が実行されます：\n"
                "1. ファイル一括アップロード\n"
                "2. データエントリー登録\n"
                "3. 試料情報の保存\n\n"
                "処理には時間がかかる場合があります。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                print("[INFO] ユーザーがデータ登録をキャンセルしました")
                return
            
            # 段階1: ファイル一括アップロード
            print("[INFO] 段階1: ファイル一括アップロード")
            upload_success = self._execute_batch_upload()
            
            if not upload_success:
                QMessageBox.warning(self, "エラー", "ファイルアップロードに失敗したため、データ登録を中断します。")
                return
            
            # 段階2: データ登録実行
            print("[INFO] 段階2: データ登録実行")
            registration_success = self._execute_data_registration()
            
            if registration_success:
                QMessageBox.information(self, "完了", "データ登録が正常に完了しました。")
            else:
                QMessageBox.warning(self, "エラー", "データ登録に失敗しました。詳細はログを確認してください。")
            
        except Exception as e:
            print(f"[ERROR] データ登録処理エラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"データ登録処理でエラーが発生しました:\n{str(e)}")
    
    def _execute_batch_upload(self) -> bool:
        """ファイル一括アップロードを実行"""
        try:
            # ベアラートークンを取得（親から継承またはファイルから読み取り）
            bearer_token = getattr(self, 'bearer_token', None)
            if not bearer_token:
                print("[DEBUG] Bearer トークンが親から取得できない - 他の方法を試行")
                
                # 親ウィジェットから取得を試行（複数階層遡及）
                current_widget = self
                while current_widget and not bearer_token:
                    current_widget = current_widget.parent()
                    if current_widget and hasattr(current_widget, 'bearer_token'):
                        bearer_token = current_widget.bearer_token
                        print(f"[DEBUG] 親ウィジェット({type(current_widget).__name__})からBearerトークンを取得")
                        break
                
                # ファイルから読み取り
                if not bearer_token:
                    print("[DEBUG] ファイルからBearerトークンを読み取り試行")
                    from config.common import BEARER_TOKEN_FILE
                    try:
                        if os.path.exists(BEARER_TOKEN_FILE):
                            with open(BEARER_TOKEN_FILE, 'r', encoding='utf-8') as f:
                                file_token = f.read().strip()
                            # ファイルから読み取ったトークンの形式をチェック
                            if file_token.startswith('BearerToken='):
                                bearer_token = file_token[12:]  # 'BearerToken='プレフィックスを除去
                            elif file_token.startswith('Bearer '):
                                bearer_token = file_token[7:]  # 'Bearer 'プレフィックスを除去
                            elif file_token:
                                bearer_token = file_token
                            print(f"[DEBUG] ファイルからBearerトークンを取得: 長さ={len(bearer_token) if bearer_token else 0}")
                    except Exception as e:
                        print(f"[WARNING] Bearerトークンファイル読み取りエラー: {e}")
            
            if not bearer_token:
                print("[ERROR] Bearerトークンが取得できません")
                return False
                
            # データセット情報取得
            dataset_info = getattr(self.file_set, 'dataset_info', None)
            extended_config = getattr(self.file_set, 'extended_config', {})
            dataset_id = None
            
            if dataset_info and dataset_info.get('id'):
                dataset_id = dataset_info['id']
            elif extended_config.get('dataset_id'):
                dataset_id = extended_config['dataset_id']
            
            if not dataset_id:
                print("[ERROR] データセットIDが取得できません")
                return False
            
            # 対象ファイル取得
            valid_items = self.file_set.get_valid_items()
            file_items = [item for item in valid_items if item.file_type == FileType.FILE]
            display_items = self._get_display_file_items(file_items)
            
            # マッピングファイル追加
            mapping_file_path = self._get_mapping_file_path()
            mapping_item = None
            if mapping_file_path and os.path.exists(mapping_file_path):
                mapping_item = FileItem(
                    path=mapping_file_path,
                    relative_path="path_mapping.xlsx",
                    name="path_mapping.xlsx",
                    file_type=FileType.FILE,
                    item_type=FileItemType.ATTACHMENT  # 添付ファイルとして設定
                )
                print(f"[DEBUG] path_mapping.xlsx を添付ファイルとして追加: {mapping_file_path}")
                display_items.append(mapping_item)
            
            total_files = len(display_items)
            
            # プログレスダイアログ
            progress = QProgressDialog("ファイルアップロード中...", "キャンセル", 0, total_files, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            
            # アップロード実行
            upload_results = []
            failed_files = []
            
            for i, file_item in enumerate(display_items):
                if progress.wasCanceled():
                    print("[INFO] アップロードがキャンセルされました")
                    progress.close()
                    return False
                
                progress.setLabelText(f"アップロード中: {file_item.name} ({i+1}/{total_files})")
                progress.setValue(i)
                QApplication.processEvents()
                
                try:
                    upload_result = self._execute_single_upload(bearer_token, dataset_id, file_item)
                    
                    if upload_result and upload_result.get('upload_id'):
                        upload_id = upload_result['upload_id']
                        setattr(file_item, 'upload_id', upload_id)
                        setattr(file_item, 'upload_response', upload_result.get('response_data', {}))
                        upload_results.append(upload_result)
                        print(f"[SUCCESS] {file_item.name} -> ID: {upload_id}")
                    else:
                        error_detail = upload_result.get('error', '不明なエラー') if upload_result else 'レスポンスなし'
                        failed_files.append((file_item.name, error_detail))
                        print(f"[ERROR] {file_item.name} -> {error_detail}")
                        
                except Exception as e:
                    error_msg = str(e)
                    failed_files.append((file_item.name, error_msg))
                    print(f"[ERROR] {file_item.name} -> 例外: {error_msg}")
            
            progress.setValue(total_files)
            progress.close()
            
            # 結果判定
            success_count = len(upload_results)
            failed_count = len(failed_files)
            
            print(f"[INFO] アップロード結果: 成功={success_count}, 失敗={failed_count}")
            
            if failed_count == 0:
                return True
            elif success_count > 0:
                # 一部成功の場合は続行可能
                reply = QMessageBox.question(
                    self, "一部アップロード失敗", 
                    f"アップロードの一部が失敗しました:\n"
                    f"成功: {success_count}個\n"
                    f"失敗: {failed_count}個\n\n"
                    f"成功したファイルでデータ登録を続行しますか？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                return reply == QMessageBox.Yes
            else:
                # 全て失敗
                return False
                
        except Exception as e:
            print(f"[ERROR] 一括アップロード実行エラー: {e}")
            return False
    
    def _execute_data_registration(self) -> bool:
        """データ登録を実行"""
        try:
            bearer_token = getattr(self, 'bearer_token', None)
            
            # ファイルセット状態詳細確認
            print(f"[DEBUG] データ登録実行 - ファイルセット詳細確認:")
            print(f"  - name: {getattr(self.file_set, 'name', 'None')}")
            print(f"  - dataset_id: {getattr(self.file_set, 'dataset_id', 'None')}")
            print(f"  - dataset_info: {getattr(self.file_set, 'dataset_info', 'None')}")
            print(f"  - extended_config keys: {list(getattr(self.file_set, 'extended_config', {}).keys())}")
            
            # データセット情報を取得（複数の方法を試行）
            dataset_info = None
            
            # 方法1: dataset_info属性から直接取得
            if hasattr(self.file_set, 'dataset_info') and self.file_set.dataset_info:
                dataset_info = self.file_set.dataset_info
                print(f"[DEBUG] データセット情報取得成功 (dataset_info): {dataset_info}")
            
            # 方法2: dataset_id属性から構築
            elif hasattr(self.file_set, 'dataset_id') and self.file_set.dataset_id:
                dataset_info = {'id': self.file_set.dataset_id}
                print(f"[DEBUG] データセット情報構築 (dataset_id): {dataset_info}")
            
            # 方法3: extended_configから取得
            elif hasattr(self.file_set, 'extended_config') and self.file_set.extended_config:
                extended_config = self.file_set.extended_config
                if 'selected_dataset' in extended_config:
                    selected_dataset = extended_config['selected_dataset']
                    if isinstance(selected_dataset, dict) and 'id' in selected_dataset:
                        dataset_info = selected_dataset
                        print(f"[DEBUG] データセット情報取得 (extended_config): {dataset_info}")
                    elif isinstance(selected_dataset, str):
                        dataset_info = {'id': selected_dataset}
                        print(f"[DEBUG] データセット情報構築 (extended_config str): {dataset_info}")
            
            if not dataset_info or not dataset_info.get('id'):
                print(f"[ERROR] データセット情報が取得できません - ファイルセット全属性:")
                print(f"  {vars(self.file_set)}")
                return False
            
            # アップロード済みファイルを取得
            valid_items = self.file_set.get_valid_items()
            file_items = [item for item in valid_items if item.file_type == FileType.FILE]
            display_items = self._get_display_file_items(file_items)
            
            # マッピングファイルも含める
            mapping_file_path = self._get_mapping_file_path()
            if mapping_file_path and os.path.exists(mapping_file_path):
                mapping_item = FileItem(
                    path=mapping_file_path,
                    relative_path="path_mapping.xlsx",
                    name="path_mapping.xlsx",
                    file_type=FileType.FILE,
                    item_type=FileItemType.ATTACHMENT  # 添付ファイルとして設定
                )
                print(f"[DEBUG] path_mapping.xlsx を添付ファイルとして設定: {mapping_file_path}")
                # マッピングファイルにアップロードIDがあるかチェック
                for item in display_items:
                    if item.name == "path_mapping.xlsx" and hasattr(item, 'upload_id'):
                        mapping_item = item
                        mapping_item.item_type = FileItemType.ATTACHMENT  # 既存アイテムも添付ファイルに設定
                        break
                else:
                    display_items.append(mapping_item)
            
            # アップロードIDが設定されているファイルのみ
            uploaded_files = []
            for item in display_items:
                if hasattr(item, 'upload_id') and item.upload_id:
                    uploaded_files.append(item)
            
            if not uploaded_files:
                print("[ERROR] アップロード済みファイルが見つかりません")
                return False
            
            # フォーム値とペイロード構築
            form_values = self._build_form_values_from_fileset()
            dataFiles, attachments = self._build_files_payload(uploaded_files)
            
            if not dataFiles.get('data') and not attachments:
                print("[ERROR] データファイルまたは添付ファイルが必要です")
                return False
            
            # プログレスダイアログ
            progress = QProgressDialog("データ登録中...", None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            
            try:
                # entry_dataを呼び出し
                from ..core.data_register_logic import entry_data
                
                result = entry_data(
                    bearer_token=bearer_token,
                    dataFiles=dataFiles,
                    attachements=attachments,
                    dataset_info=dataset_info,
                    form_values=form_values,
                    progress=progress
                )
                
                progress.close()
                
                if result and not result.get('error'):
                    # 成功処理
                    print("[SUCCESS] データ登録完了")
                    
                    # 試料ID保存
                    sample_info = self._extract_sample_info_from_response(result)
                    if sample_info:
                        self._save_sample_info_to_fileset(sample_info)
                    
                    return True
                else:
                    # エラー処理
                    error_detail = result.get('detail', '不明なエラー') if result else 'レスポンスなし'
                    print(f"[ERROR] データ登録エラー: {error_detail}")
                    return False
                
            except Exception as e:
                progress.close()
                print(f"[ERROR] entry_data呼び出しエラー: {e}")
                return False
            
        except Exception as e:
            print(f"[ERROR] データ登録実行エラー: {e}")
            return False
    
    def _save_sample_info_to_fileset(self, sample_info: dict):
        """試料情報をファイルセットに保存"""
        try:
            if not hasattr(self.file_set, 'extended_config'):
                self.file_set.extended_config = {}
            
            self.file_set.extended_config['last_sample_id'] = sample_info['sample_id']
            self.file_set.extended_config['last_sample_name'] = sample_info.get('sample_name', '')
            self.file_set.extended_config['registration_timestamp'] = str(datetime.now().isoformat())
            
            print(f"[INFO] 試料情報保存完了: ID={sample_info['sample_id']}")
            
        except Exception as e:
            print(f"[WARNING] 試料情報保存エラー: {e}")
    
    def _build_form_values_from_fileset(self) -> dict:
        """ファイルセット情報からフォーム値を構築（通常登録との互換性確保）"""
        try:
            form_values = {}
            extended_config = getattr(self.file_set, 'extended_config', {})
            
            # 基本情報（extended_configを優先）
            form_values['dataName'] = extended_config.get('data_name') or getattr(self.file_set, 'data_name', '') or f"一括登録_{self.file_set.name}"
            form_values['basicDescription'] = extended_config.get('description') or getattr(self.file_set, 'description', '') or "一括登録によるデータ"
            form_values['experimentId'] = extended_config.get('experiment_id') or getattr(self.file_set, 'experiment_id', '') or ""
            
            # 試料情報の処理
            sample_mode = extended_config.get('sample_mode') or getattr(self.file_set, 'sample_mode', 'new')
            sample_id_from_config = extended_config.get('sample_id') or getattr(self.file_set, 'sample_id', '')
            
            print(f"[DEBUG] 試料モード判定: sample_mode='{sample_mode}', sample_id='{sample_id_from_config}'")
            
            # 試料モードによる分岐処理（通常登録と同じ仕様）
            if sample_mode == 'existing' and sample_id_from_config:
                # 既存試料選択の場合：sampleIdを設定
                form_values['sampleId'] = sample_id_from_config
                # 参考値として試料情報も保持（通常登録と同じ構造）
                form_values['sampleNames'] = extended_config.get('sample_name') or getattr(self.file_set, 'sample_name', '') or f"試料_{self.file_set.name}"
                form_values['sampleDescription'] = extended_config.get('sample_description') or getattr(self.file_set, 'sample_description', '') or "一括登録試料"
                form_values['sampleComposition'] = extended_config.get('sample_composition') or getattr(self.file_set, 'sample_composition', '') or ""
                print(f"[DEBUG] 既存試料ID設定: {sample_id_from_config}")
            else:
                # 新規作成の場合：sampleNamesを設定（通常登録と同じ）
                form_values['sampleNames'] = extended_config.get('sample_name') or getattr(self.file_set, 'sample_name', '') or f"試料_{self.file_set.name}"
                form_values['sampleDescription'] = extended_config.get('sample_description') or getattr(self.file_set, 'sample_description', '') or "一括登録試料"
                form_values['sampleComposition'] = extended_config.get('sample_composition') or getattr(self.file_set, 'sample_composition', '') or ""
                # 追加の新規試料情報
                form_values['sampleReferenceUrl'] = extended_config.get('reference_url') or getattr(self.file_set, 'reference_url', '') or ""
                form_values['sampleTags'] = extended_config.get('tags') or getattr(self.file_set, 'tags', '') or ""
                print(f"[DEBUG] 新規試料情報設定完了: {form_values['sampleNames']}")
            
            # 固有情報（カスタム値）の抽出 - ファイルセット属性とextended_configから
            custom_values = getattr(self.file_set, 'custom_values', {}) or extended_config.get('custom_values', {})
            
            if not custom_values:
                # custom_valuesが空の場合、extended_configから直接抽出
                custom_values = {}
                exclude_keys = {
                    'data_name', 'description', 'experiment_id', 'reference_url', 'tags',
                    'sample_mode', 'sample_id', 'sample_name', 'sample_description', 
                    'sample_composition', 'dataset_id', 'dataset_name',
                    'temp_folder', 'temp_created', 'mapping_file', 'last_sample_id',
                    'last_sample_name', 'registration_timestamp', 'selected_dataset'
                }
                for key, value in extended_config.items():
                    if key not in exclude_keys and value is not None and value != "":
                        custom_values[key] = value
                        print(f"[DEBUG] カスタム値抽出: {key} = {value}")
            
            form_values['custom'] = custom_values
            
            print(f"[DEBUG] 構築されたフォーム値: dataName='{form_values['dataName']}', sampleId='{form_values.get('sampleId', 'new')}', custom={len(custom_values)}項目")
            return form_values
            
        except Exception as e:
            print(f"[ERROR] フォーム値構築エラー: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _build_files_payload(self, uploaded_files: List[FileItem]) -> Tuple[dict, List[dict]]:
        """アップロード済みファイルからペイロードを構築"""
        try:
            dataFiles = {"data": []}
            attachments = []
            
            for file_item in uploaded_files:
                upload_id = getattr(file_item, 'upload_id', None)
                if not upload_id:
                    continue
                
                # ファイルの種別を取得（テーブルから）
                file_type_category = self._get_file_type_from_table(file_item)
                
                if file_type_category == "データファイル":
                    dataFiles["data"].append({
                        "type": "upload",
                        "id": upload_id
                    })
                else:  # "添付ファイル"
                    attachments.append({
                        "uploadId": upload_id,
                        "description": file_item.name
                    })
            
            print(f"[DEBUG] データファイル数: {len(dataFiles['data'])}")
            print(f"[DEBUG] 添付ファイル数: {len(attachments)}")
            
            return dataFiles, attachments
            
        except Exception as e:
            print(f"[ERROR] ファイルペイロード構築エラー: {e}")
            return {"data": []}, []
    
    def _get_file_type_from_table(self, file_item: FileItem) -> str:
        """テーブルからファイルの種別を取得"""
        try:
            # ファイルテーブルから該当行を探す
            for row in range(self.files_table.rowCount()):
                name_item = self.files_table.item(row, 1)  # 登録ファイル名列
                if name_item and file_item.name in name_item.text():
                    # 種別列（3列目）からコンボボックスの値を取得
                    type_widget = self.files_table.cellWidget(row, 3)
                    if isinstance(type_widget, QComboBox):
                        return type_widget.currentText()
            
            # デフォルトは拡張子ベースで判定
            return self._get_file_type_category(file_item)
            
        except Exception as e:
            print(f"[WARNING] ファイル種別取得エラー: {e}")
            return "添付ファイル"  # デフォルト
    
    def _extract_sample_info_from_response(self, response_data: dict) -> Optional[dict]:
        """レスポンスから試料情報を抽出"""
        try:
            data = response_data.get('data', {})
            relationships = data.get('relationships', {})
            sample_data = relationships.get('sample', {}).get('data', {})
            
            if sample_data and sample_data.get('id'):
                return {
                    'sample_id': sample_data['id'],
                    'sample_name': f"Sample_{sample_data['id'][:8]}"
                }
            
            return None
            
        except Exception as e:
            print(f"[WARNING] 試料情報抽出エラー: {e}")
            return None
    
    def _format_size(self, size_bytes: int) -> str:
        """ファイルサイズを人間が読みやすい形式に変換"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)
        while size >= 1024 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.1f} {size_names[i]}"
    
    def get_validated_file_sets(self) -> List[FileSet]:
        """検証済みファイルセットを取得（重複ファイル除外後）"""
        return self.file_sets


class BatchRegisterPreviewDialog(QDialog):
    """一括登録プレビューダイアログ（複数ファイルセット対応）"""
    
    def __init__(self, file_sets: List[FileSet], parent=None, bearer_token: str = None):
        super().__init__(parent)
        self.file_sets = file_sets
        self.duplicate_files = set()
        self.bearer_token = bearer_token
        self.setWindowTitle("一括登録プレビュー（複数ファイルセット）")
        self.setModal(True)
        
        # ダイアログサイズをディスプレイの90%に設定
        self.setup_dialog_size()
        
        self.setup_ui()
        self.check_duplicates()
        self.load_data()
    
    def setup_dialog_size(self):
        """ダイアログサイズを設定（ディスプレイ高さの90%）"""
        try:
            from PyQt5.QtWidgets import QDesktopWidget
            desktop = QDesktopWidget()
            screen_rect = desktop.screenGeometry()
            
            # ディスプレイサイズの90%に設定
            target_width = int(screen_rect.width() * 0.9)
            target_height = int(screen_rect.height() * 0.9)
            
            # 最小サイズを設定
            min_width = 1000
            min_height = 700
            target_width = max(target_width, min_width)
            target_height = max(target_height, min_height)
            
            self.resize(target_width, target_height)
            
            # ダイアログを画面中央に配置
            self.move(
                (screen_rect.width() - target_width) // 2,
                (screen_rect.height() - target_height) // 2
            )
            
            print(f"[DEBUG] 複数ファイルセットプレビューダイアログサイズ設定: {target_width}x{target_height}")
        except Exception as e:
            print(f"[WARNING] ダイアログサイズ設定エラー: {e}")
            self.resize(1200, 800)  # フォールバック
    
    def setup_ui(self):
        """UIセットアップ"""
        layout = QVBoxLayout()
        
        # 上部: サマリー情報
        summary_group = QGroupBox("一括登録サマリー")
        summary_layout = QVBoxLayout()
        
        self.summary_label = QLabel()
        self.summary_label.setFont(QFont("", 10, QFont.Bold))
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        
        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)
        
        # 中央: ファイルセットタブ
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget, 1)
        
        # 下部: 一括処理ボタンとダイアログボタン
        buttons_layout = QVBoxLayout()
        
        # 一括処理ボタン
        batch_buttons_layout = QHBoxLayout()
        
        self.batch_upload_all_button = QPushButton("全ファイルセット一括アップロード")
        self.batch_upload_all_button.clicked.connect(self._batch_upload_all)
        self.batch_upload_all_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        self.batch_register_all_button = QPushButton("全ファイルセット一括データ登録")
        self.batch_register_all_button.clicked.connect(self._batch_register_all)
        self.batch_register_all_button.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        
        batch_buttons_layout.addWidget(self.batch_upload_all_button)
        batch_buttons_layout.addWidget(self.batch_register_all_button)
        batch_buttons_layout.addStretch()
        
        buttons_layout.addLayout(batch_buttons_layout)
        
        # ダイアログボタン
        dialog_button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dialog_button_box.accepted.connect(self.accept)
        dialog_button_box.rejected.connect(self.reject)
        buttons_layout.addWidget(dialog_button_box)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
    
    def check_duplicates(self):
        """ファイル重複をチェック（複数ファイルセット間）"""
        file_paths = {}  # path -> [file_set_names]
        
        try:
            for file_set in self.file_sets:
                if not file_set:
                    continue
                    
                valid_items = file_set.get_valid_items()
                for item in valid_items:
                    if item.file_type == FileType.FILE and item.path:
                        if item.path not in file_paths:
                            file_paths[item.path] = []
                        file_paths[item.path].append(file_set.name)
            
            # 重複ファイルを特定
            for path, file_set_names in file_paths.items():
                if len(file_set_names) > 1:
                    self.duplicate_files.add(path)
                    print(f"[WARNING] 重複ファイル検出: {path} → {', '.join(file_set_names)}")
                    
        except Exception as e:
            print(f"重複チェック中にエラー: {e}")
    
    def load_data(self):
        """データを読み込み"""
        try:
            # サマリー情報
            total_filesets = len(self.file_sets)
            
            if total_filesets == 0:
                self.summary_label.setText("ファイルセットがありません")
                return
            
            total_files = 0
            total_size = 0
            datasets_count = 0
            dataset_names = set()
            
            for fs in self.file_sets:
                if fs:
                    try:
                        valid_items = [item for item in fs.get_valid_items() if item.file_type == FileType.FILE]
                        total_files += len(valid_items)
                        total_size += fs.get_total_size()
                        
                        # データセット情報集計
                        if hasattr(fs, 'dataset_id') and fs.dataset_id:
                            dataset_names.add(fs.dataset_id)
                        elif hasattr(fs, 'dataset_info') and fs.dataset_info:
                            if isinstance(fs.dataset_info, dict) and fs.dataset_info.get('id'):
                                dataset_names.add(fs.dataset_info['id'])
                            elif isinstance(fs.dataset_info, str):
                                dataset_names.add(fs.dataset_info)
                    except Exception as e:
                        print(f"ファイルセット '{fs.name}' の統計取得中にエラー: {e}")
            
            datasets_count = len(dataset_names)
            duplicate_count = len(self.duplicate_files)
            
            summary_text = f"""一括登録対象情報:
• ファイルセット数: {total_filesets}個
• 対象データセット数: {datasets_count}個
• 総ファイル数: {total_files}個
• 総サイズ: {self._format_size(total_size)}"""
            
            if duplicate_count > 0:
                summary_text += f"\n• <font color='red'>⚠ 重複ファイル: {duplicate_count}個</font>"
            
            if datasets_count > 0:
                summary_text += f"\n\n対象データセット: {', '.join(list(dataset_names)[:5])}"
                if len(dataset_names) > 5:
                    summary_text += f" 他{len(dataset_names) - 5}個"
            
            self.summary_label.setText(summary_text)
            
            # ファイルセットタブを作成
            for i, file_set in enumerate(self.file_sets):
                if not file_set:
                    continue
                    
                try:
                    preview_widget = FileSetPreviewWidget(file_set, self.duplicate_files, self.bearer_token)
                    tab_name = file_set.name or f"ファイルセット{i+1}"
                    
                    # データセット情報表示
                    dataset_info = ""
                    if hasattr(file_set, 'dataset_info') and file_set.dataset_info:
                        if isinstance(file_set.dataset_info, dict):
                            dataset_name = file_set.dataset_info.get('name', file_set.dataset_info.get('id', ''))
                            dataset_info = f" [{dataset_name[:15]}...]"
                        else:
                            dataset_info = f" [{str(file_set.dataset_info)[:15]}...]"
                    elif hasattr(file_set, 'dataset_id') and file_set.dataset_id:
                        dataset_info = f" [{file_set.dataset_id[:15]}...]"
                    
                    # 重複ファイルがある場合は警告アイコンを追加
                    has_duplicates = False
                    for item in (file_set.items or []):
                        if hasattr(item, 'path') and item.path in self.duplicate_files:
                            has_duplicates = True
                            break
                    
                    if has_duplicates:
                        tab_name += " ⚠"  # 重複アイコン
                    
                    tab_name += dataset_info
                    
                    # タブ名が長すぎる場合は省略
                    if len(tab_name) > 50:
                        tab_name = tab_name[:47] + "..."
                    
                    self.tab_widget.addTab(preview_widget, tab_name)
                except Exception as e:
                    print(f"ファイルセット '{file_set.name}' のタブ作成中にエラー: {e}")
                    # エラーが発生したファイルセットのタブには簡易メッセージを表示
                    error_widget = QLabel(f"エラー: {str(e)}")
                    self.tab_widget.addTab(error_widget, f"{file_set.name or 'エラー'} ❌")
                    
        except Exception as e:
            print(f"複数ファイルセットプレビューデータ読み込み中にエラー: {e}")
            self.summary_label.setText(f"エラー: {str(e)}")
    
    def _batch_upload_all(self):
        """全ファイルセット一括アップロード処理（Bearer Token自動選択対応）"""
        try:
            print("[INFO] 全ファイルセット一括アップロード開始")
            
            # 注意: Bearer Tokenは不要（API呼び出し時に自動選択される）
            
            # アップロード対象ファイルセット確認
            valid_file_sets = [fs for fs in self.file_sets if fs and hasattr(fs, 'dataset_info') and fs.dataset_info]
            
            if not valid_file_sets:
                QMessageBox.warning(self, "エラー", "データセットが設定されたファイルセットがありません。")
                return
            
            # 確認ダイアログ
            total_files = 0
            for fs in valid_file_sets:
                valid_items = fs.get_valid_items()
                file_items = [item for item in valid_items if item.file_type == FileType.FILE]
                display_items = self._get_display_file_items_for_fileset(fs, file_items)
                total_files += len(display_items)
            
            reply = QMessageBox.question(
                self, "全ファイルセット一括アップロード確認", 
                f"全ファイルセット（{len(valid_file_sets)}個）の一括アップロードを実行しますか？\n\n"
                f"対象ファイル数: {total_files}個\n"
                f"処理には時間がかかる場合があります。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                print("[INFO] ユーザーが全ファイルセット一括アップロードをキャンセルしました")
                return
            
            # プログレスダイアログ
            progress = QProgressDialog("全ファイルセット一括アップロード中...", "キャンセル", 0, len(valid_file_sets), self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            
            # 結果集計
            total_uploaded = 0
            total_failed = 0
            fileset_results = []
            
            for i, file_set in enumerate(valid_file_sets):
                if progress.wasCanceled():
                    print("[INFO] ユーザーによりアップロードがキャンセルされました")
                    break
                
                progress.setLabelText(f"アップロード中: {file_set.name} ({i+1}/{len(valid_file_sets)})")
                progress.setValue(i)
                QApplication.processEvents()
                
                try:
                    upload_result = self._upload_single_fileset(None, file_set)
                    success_count = upload_result.get('success_count', 0)
                    failed_count = upload_result.get('failed_count', 0)
                    
                    fileset_results.append({
                        'name': file_set.name,
                        'success': success_count,
                        'failed': failed_count
                    })
                    
                    total_uploaded += success_count
                    total_failed += failed_count
                    
                    print(f"[INFO] {file_set.name}: 成功={success_count}, 失敗={failed_count}")
                    
                except Exception as e:
                    print(f"[ERROR] ファイルセット '{file_set.name}' のアップロードエラー: {e}")
                    fileset_results.append({
                        'name': file_set.name,
                        'success': 0,
                        'failed': 1,
                        'error': str(e)
                    })
                    total_failed += 1
            
            progress.setValue(len(valid_file_sets))
            progress.close()
            
            # 結果表示
            result_message = f"""全ファイルセット一括アップロード完了

全体結果:
• 対象ファイルセット: {len(valid_file_sets)}個
• 成功ファイル数: {total_uploaded}個
• 失敗ファイル数: {total_failed}個

ファイルセット別結果:"""
            
            for result in fileset_results[:10]:  # 最初の10件まで表示
                result_message += f"\n• {result['name']}: 成功={result['success']}, 失敗={result['failed']}"
                if 'error' in result:
                    result_message += f" (エラー: {result['error'][:30]}...)"
            
            if len(fileset_results) > 10:
                result_message += f"\n... 他{len(fileset_results) - 10}件"
            
            if total_failed == 0:
                QMessageBox.information(self, "アップロード完了", result_message)
            else:
                QMessageBox.warning(self, "アップロード完了（一部失敗）", result_message)
            
            print(f"[INFO] 全ファイルセット一括アップロード完了: 成功={total_uploaded}, 失敗={total_failed}")
            
        except Exception as e:
            print(f"[ERROR] 全ファイルセット一括アップロード処理エラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"全ファイルセット一括アップロード処理でエラーが発生しました:\n{str(e)}")
    
    def _batch_register_all(self):
        """全ファイルセット一括データ登録処理（Bearer Token自動選択対応）"""
        try:
            print("[INFO] 全ファイルセット一括データ登録開始")
            
            # 注意: Bearer Tokenは不要（API呼び出し時に自動選択される）
            
            # データ登録対象ファイルセット確認（デバッグログ付き）
            print(f"[DEBUG] 全体のファイルセット数: {len(self.file_sets)}")
            
            valid_file_sets = []
            for i, fs in enumerate(self.file_sets):
                print(f"[DEBUG] ファイルセット{i}: {fs.name if fs else 'None'}")
                if fs:
                    has_dataset_info = hasattr(fs, 'dataset_info')
                    dataset_info_value = getattr(fs, 'dataset_info', None) if has_dataset_info else None
                    has_dataset_id = hasattr(fs, 'dataset_id')
                    dataset_id_value = getattr(fs, 'dataset_id', None) if has_dataset_id else None
                    
                    print(f"[DEBUG]   - hasattr(dataset_info): {has_dataset_info}")
                    print(f"[DEBUG]   - dataset_info: {dataset_info_value}")
                    print(f"[DEBUG]   - hasattr(dataset_id): {has_dataset_id}")
                    print(f"[DEBUG]   - dataset_id: {dataset_id_value}")
                    
                    # dataset_info または dataset_id のいずれかがあれば有効とする
                    if (has_dataset_info and dataset_info_value) or (has_dataset_id and dataset_id_value):
                        valid_file_sets.append(fs)
                        print(f"[DEBUG]   -> 有効なファイルセット")
                    else:
                        print(f"[DEBUG]   -> 無効なファイルセット（データセット未設定）")
                else:
                    print(f"[DEBUG]   -> Noneファイルセット")
            
            print(f"[DEBUG] 有効なファイルセット数: {len(valid_file_sets)}")
            
            if not valid_file_sets:
                QMessageBox.warning(self, "エラー", "データセットが設定されたファイルセットがありません。")
                return
            
            # 前回と同じ試料IDを使用するファイルセットの確認
            same_as_previous_sets = []
            for fs in valid_file_sets:
                sample_mode = getattr(fs, 'sample_mode', 'new')
                extended_config = getattr(fs, 'extended_config', {})
                if sample_mode == 'same_as_previous' or extended_config.get('sample_mode') == '前回と同じ':
                    same_as_previous_sets.append(fs)
            
            # 確認ダイアログ
            total_files = 0
            for fs in valid_file_sets:
                valid_items = fs.get_valid_items()
                file_items = [item for item in valid_items if item.file_type == FileType.FILE]
                display_items = self._get_display_file_items_for_fileset(fs, file_items)
                total_files += len(display_items)
            
            confirmation_text = f"全ファイルセット（{len(valid_file_sets)}個）の一括データ登録を実行しますか？\n\n"
            confirmation_text += f"対象ファイル数: {total_files}個\n"
            
            if same_as_previous_sets:
                confirmation_text += f"「前回と同じ」試料モード: {len(same_as_previous_sets)}個\n"
            
            confirmation_text += "\n実行内容:\n1. ファイル一括アップロード\n2. データエントリー登録\n3. 試料ID継承処理\n\n処理には時間がかかる場合があります。"
            
            reply = QMessageBox.question(
                self, "全ファイルセット一括データ登録確認", 
                confirmation_text,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                print("[INFO] ユーザーが全ファイルセット一括データ登録をキャンセルしました")
                return
            
            # プログレスダイアログ
            progress = QProgressDialog("全ファイルセット一括データ登録中...", "キャンセル", 0, len(valid_file_sets), self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()
            
            # 結果集計
            total_registered = 0
            total_failed = 0
            fileset_results = []
            previous_sample_id = None  # 前回のサンプルIDを保存
            
            for i, file_set in enumerate(valid_file_sets):
                if progress.wasCanceled():
                    print("[INFO] ユーザーによりデータ登録がキャンセルされました")
                    break
                
                progress.setLabelText(f"データ登録中: {file_set.name} ({i+1}/{len(valid_file_sets)})")
                progress.setValue(i)
                QApplication.processEvents()
                
                try:
                    # 前回と同じ試料IDを使用する場合の処理
                    sample_mode = getattr(file_set, 'sample_mode', 'new')
                    extended_config = getattr(file_set, 'extended_config', {})
                    
                    if (sample_mode == 'same_as_previous' or extended_config.get('sample_mode') == '前回と同じ') and previous_sample_id:
                        # 前回のサンプルIDを設定
                        file_set.sample_mode = 'existing'
                        file_set.sample_id = previous_sample_id
                        if not hasattr(file_set, 'extended_config'):
                            file_set.extended_config = {}
                        file_set.extended_config['sample_mode'] = '既存試料使用'
                        file_set.extended_config['sample_id'] = previous_sample_id
                        print(f"[INFO] 前回サンプルID継承: {file_set.name} -> {previous_sample_id}")
                    
                    register_result = self._register_single_fileset(None, file_set)
                    
                    if register_result.get('success'):
                        fileset_results.append({
                            'name': file_set.name,
                            'success': True,
                            'sample_id': register_result.get('sample_id')
                        })
                        
                        total_registered += 1
                        
                        # 次回用に試料IDを保存
                        sample_id = register_result.get('sample_id')
                        if sample_id:
                            previous_sample_id = sample_id
                        
                        print(f"[SUCCESS] {file_set.name}: 登録完了, sample_id={sample_id}")
                    else:
                        error_detail = register_result.get('error', '不明なエラー')
                        fileset_results.append({
                            'name': file_set.name,
                            'success': False,
                            'error': error_detail
                        })
                        total_failed += 1
                        print(f"[ERROR] {file_set.name}: 登録失敗 - {error_detail}")
                    
                except Exception as e:
                    print(f"[ERROR] ファイルセット '{file_set.name}' のデータ登録エラー: {e}")
                    fileset_results.append({
                        'name': file_set.name,
                        'success': False,
                        'error': str(e)
                    })
                    total_failed += 1
            
            progress.setValue(len(valid_file_sets))
            progress.close()
            
            # 結果表示
            result_message = f"""全ファイルセット一括データ登録完了

全体結果:
• 対象ファイルセット: {len(valid_file_sets)}個
• 登録成功: {total_registered}個
• 登録失敗: {total_failed}個

ファイルセット別結果:"""
            
            for result in fileset_results[:8]:  # 最初の8件まで表示
                if result['success']:
                    sample_info = f" (試料ID: {result['sample_id'][:8]}...)" if result.get('sample_id') else ""
                    result_message += f"\n✓ {result['name']}: 成功{sample_info}"
                else:
                    error_info = result.get('error', '不明なエラー')
                    result_message += f"\n✗ {result['name']}: 失敗 ({error_info[:20]}...)"
            
            if len(fileset_results) > 8:
                result_message += f"\n... 他{len(fileset_results) - 8}件"
            
            if total_failed == 0:
                QMessageBox.information(self, "データ登録完了", result_message)
            else:
                QMessageBox.warning(self, "データ登録完了（一部失敗）", result_message)
            
            print(f"[INFO] 全ファイルセット一括データ登録完了: 成功={total_registered}, 失敗={total_failed}")
            
        except Exception as e:
            print(f"[ERROR] 全ファイルセット一括データ登録処理エラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"全ファイルセット一括データ登録処理でエラーが発生しました:\n{str(e)}")
    
    def _upload_single_fileset(self, bearer_token: str, file_set: FileSet) -> dict:
        """単一ファイルセットのアップロード処理"""
        try:
            print(f"[INFO] ファイルセットアップロード開始: {file_set.name}")
            
            # ファイルセット状態デバッグ出力
            print(f"[DEBUG] FileSet属性確認:")
            print(f"  - dataset_id: {getattr(file_set, 'dataset_id', 'None')}")
            print(f"  - dataset_info: {getattr(file_set, 'dataset_info', 'None')}")
            print(f"  - extended_config keys: {list(getattr(file_set, 'extended_config', {}).keys())}")
            
            # データセット情報取得
            dataset_info = getattr(file_set, 'dataset_info', None)
            dataset_id = None
            
            # 優先順位1: dataset_id属性から直接取得
            if hasattr(file_set, 'dataset_id') and file_set.dataset_id:
                dataset_id = file_set.dataset_id
                print(f"[DEBUG] データセットID取得: file_set.dataset_id = {dataset_id}")
            # 優先順位2: dataset_infoから取得
            elif dataset_info and isinstance(dataset_info, dict):
                dataset_id = dataset_info.get('id')
                print(f"[DEBUG] データセットID取得: dataset_info['id'] = {dataset_id}")
            elif dataset_info and isinstance(dataset_info, str):
                dataset_id = dataset_info
                print(f"[DEBUG] データセットID取得: dataset_info = {dataset_id}")
            # 優先順位3: extended_configから取得
            elif hasattr(file_set, 'extended_config') and file_set.extended_config:
                extended_config = file_set.extended_config
                if 'selected_dataset' in extended_config:
                    selected_dataset = extended_config['selected_dataset']
                    if isinstance(selected_dataset, dict) and 'id' in selected_dataset:
                        dataset_id = selected_dataset['id']
                        print(f"[DEBUG] データセットID取得: extended_config['selected_dataset']['id'] = {dataset_id}")
                    elif isinstance(selected_dataset, str):
                        dataset_id = selected_dataset
                        print(f"[DEBUG] データセットID取得: extended_config['selected_dataset'] = {dataset_id}")
            
            if not dataset_id:
                print(f"[ERROR] データセットID取得失敗 - ファイルセット詳細:")
                print(f"  - FileSet全属性: {vars(file_set)}")
                return {'success_count': 0, 'failed_count': 1, 'error': 'データセットIDが取得できません'}
            
            # 対象ファイル取得
            valid_items = file_set.get_valid_items()
            file_items = [item for item in valid_items if item.file_type == FileType.FILE]
            display_items = self._get_display_file_items_for_fileset(file_set, file_items)
            
            # マッピングファイル追加
            mapping_file_path = self._get_mapping_file_path_for_fileset(file_set)
            if mapping_file_path and os.path.exists(mapping_file_path):
                mapping_item = FileItem(
                    path=mapping_file_path,
                    relative_path="path_mapping.xlsx",
                    name="path_mapping.xlsx",
                    file_type=FileType.FILE,
                    item_type=FileItemType.ATTACHMENT  # 添付ファイルとして設定
                )
                print(f"[DEBUG] path_mapping.xlsx を添付ファイルとして追加: {mapping_file_path}")
                display_items.append(mapping_item)
            
            if not display_items:
                return {'success_count': 0, 'failed_count': 0, 'error': 'アップロード対象ファイルがありません'}
            
            # アップロード実行
            success_count = 0
            failed_count = 0
            
            for file_item in display_items:
                try:
                    # bearer_tokenは不要（自動選択される）
                    upload_result = self._execute_single_upload_for_fileset(None, dataset_id, file_item)
                    if upload_result and upload_result.get('upload_id'):
                        upload_id = upload_result['upload_id']
                        setattr(file_item, 'upload_id', upload_id)
                        setattr(file_item, 'upload_response', upload_result.get('response_data', {}))
                        # path_mapping.xlsx の場合は mapping_upload_id にセット
                        if file_item.name == "path_mapping.xlsx":
                            file_set.mapping_upload_id = upload_id
                        success_count += 1
                    else:
                        # 失敗時は mapping_upload_id をクリアしない（前回成功分を保持）
                        failed_count += 1
                except Exception as e:
                    print(f"[ERROR] ファイルアップロードエラー ({file_item.name}): {e}")
                    failed_count += 1
            print(f"[INFO] ファイルセットアップロード完了: {file_set.name} - 成功={success_count}, 失敗={failed_count}")
            return {
                'success_count': success_count,
                'failed_count': failed_count,
                'total_files': len(display_items)
            }
            
        except Exception as e:
            print(f"[ERROR] ファイルセットアップロードエラー: {e}")
            return {'success_count': 0, 'failed_count': 1, 'error': str(e)}
    
    def _register_single_fileset(self, bearer_token: str, file_set: FileSet) -> dict:
        """単一ファイルセットのデータ登録処理"""
        try:
            print(f"[INFO] ファイルセットデータ登録開始: {file_set.name}")
            
            # アップロードが先に実行されているかチェック・実行
            upload_result = self._upload_single_fileset(bearer_token, file_set)
            if upload_result['success_count'] == 0:
                return {'success': False, 'error': 'ファイルアップロードに失敗しました'}
            
            # データセット情報取得・復元
            dataset_info = getattr(file_set, 'dataset_info', None)
            extended_config = getattr(file_set, 'extended_config', {})
            
            if not dataset_info:
                # dataset_infoが不足している場合、extended_configから復元
                dataset_id = extended_config.get('dataset_id')
                if dataset_id:
                    try:
                        from config.common import OUTPUT_RDE_DIR
                        dataset_file_path = os.path.join(OUTPUT_RDE_DIR, "data", "datasets", f"{dataset_id}.json")
                        if os.path.exists(dataset_file_path):
                            with open(dataset_file_path, 'r', encoding='utf-8') as f:
                                dataset_data = json.load(f)
                            # dataset_infoとしてfile_setに設定
                            file_set.dataset_info = dataset_data
                            dataset_info = dataset_data
                            print(f"[DEBUG] ファイルセット用データセット情報復元: {dataset_data.get('attributes', {}).get('name', dataset_id)}")
                        else:
                            print(f"[WARNING] データセットファイルが見つかりません: {dataset_file_path}")
                            return {'success': False, 'error': 'データセット情報が取得できません'}
                    except Exception as e:
                        print(f"[ERROR] データセット情報復元エラー: {e}")
                        return {'success': False, 'error': f'データセット情報復元エラー: {e}'}
                else:
                    return {'success': False, 'error': 'データセット情報が設定されていません'}
            
            # アップロード済みファイルを取得
            valid_items = file_set.get_valid_items()
            file_items = [item for item in valid_items if item.file_type == FileType.FILE]
            display_items = self._get_display_file_items_for_fileset(file_set, file_items)
            
            # マッピングファイルも含める
            mapping_file_path = self._get_mapping_file_path_for_fileset(file_set)
            if mapping_file_path and os.path.exists(mapping_file_path):
                mapping_item = FileItem(
                    path=mapping_file_path,
                    relative_path="path_mapping.xlsx",
                    name="path_mapping.xlsx",
                    file_type=FileType.FILE,
                    item_type=FileItemType.ATTACHMENT  # 添付ファイルとして設定
                )
                print(f"[DEBUG] path_mapping.xlsx を添付ファイルとして設定: {mapping_file_path}")
                for item in display_items:
                    if item.name == "path_mapping.xlsx" and hasattr(item, 'upload_id'):
                        mapping_item = item
                        mapping_item.item_type = FileItemType.ATTACHMENT  # 既存アイテムも添付ファイルに設定
                        break
                else:
                    display_items.append(mapping_item)
            
            # アップロードIDが設定されているファイルのみ
            uploaded_files = [item for item in display_items if hasattr(item, 'upload_id') and item.upload_id]
            
            if not uploaded_files:
                return {'success': False, 'error': 'アップロード済みファイルが見つかりません'}
            
            # フォーム値とペイロード構築
            form_values = self._build_form_values_from_fileset(file_set)
            dataFiles, attachments = self._build_files_payload_for_fileset(file_set, uploaded_files)
            
            if not dataFiles.get('data') and not attachments:
                return {'success': False, 'error': 'データファイルまたは添付ファイルが必要です'}
            
            # entry_dataを呼び出し（bearer_token=Noneで自動選択）
            from ..core.data_register_logic import entry_data
            
            result = entry_data(
                bearer_token=None,
                dataFiles=dataFiles,
                attachements=attachments,
                dataset_info=dataset_info,
                form_values=form_values
            )
            
            if result and not result.get('error'):
                # 成功処理
                sample_info = self._extract_sample_info_from_response(result)
                if sample_info:
                    self._save_sample_info_to_fileset(file_set, sample_info)
                    return {'success': True, 'sample_id': sample_info['sample_id']}
                else:
                    return {'success': True, 'sample_id': None}
            else:
                # エラー処理
                error_detail = result.get('detail', '不明なエラー') if result else 'レスポンスなし'
                return {'success': False, 'error': error_detail}
            
        except Exception as e:
            print(f"[ERROR] ファイルセットデータ登録エラー: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_display_file_items_for_fileset(self, file_set: FileSet, file_items: List[FileItem]) -> List[FileItem]:
        """ファイルセット用の表示ファイルアイテム取得"""
        display_items = []
        zip_files_added = set()
        zip_directories = set()
        
        # ZIP化対象ディレクトリを特定
        all_items = file_set.get_valid_items()
        for item in all_items:
            if item.file_type == FileType.DIRECTORY and getattr(item, 'is_zip', False):
                zip_directories.add(item.relative_path)
        
        for item in file_items:
            # このファイルがZIP化対象ディレクトリ配下かチェック
            is_in_zip_dir = False
            zip_dir_name = None
            for zip_dir in zip_directories:
                if (item.relative_path.startswith(zip_dir + '/') or 
                    item.relative_path.startswith(zip_dir + '\\') or 
                    item.relative_path == zip_dir):
                    is_in_zip_dir = True
                    zip_dir_name = zip_dir
                    break
            
            if is_in_zip_dir and zip_dir_name:
                # ZIP化対象ディレクトリ配下のファイルの場合、ZIPファイルを表示
                zip_filename = self._get_zip_filename_for_directory_and_fileset(file_set, zip_dir_name)
                if zip_filename and zip_filename not in zip_files_added:
                    zip_item = self._create_zip_file_item_for_directory_and_fileset(file_set, zip_dir_name, zip_filename)
                    display_items.append(zip_item)
                    zip_files_added.add(zip_filename)
            else:
                # 通常のファイルはそのまま表示
                display_items.append(item)
        
        # path_mapping.xlsx を添付ファイルとして追加
        mapping_file_path = self._get_mapping_file_path_for_fileset(file_set)
        if mapping_file_path and os.path.exists(mapping_file_path):
            mapping_item = FileItem(
                path=mapping_file_path,
                relative_path="path_mapping.xlsx",
                name="path_mapping.xlsx",
                file_type=FileType.FILE,
                item_type=FileItemType.ATTACHMENT  # 添付ファイルとして設定
            )
            display_items.append(mapping_item)
            print(f"[DEBUG] path_mapping.xlsx を表示アイテムに追加: {mapping_file_path}")
        
        return display_items
    
    def _get_zip_filename_for_directory_and_fileset(self, file_set: FileSet, dir_relative_path: str) -> Optional[str]:
        """ファイルセット用のZIPファイル名取得"""
        try:
            temp_folder = getattr(file_set, 'temp_folder_path', None)
            if not temp_folder:
                extended_config = getattr(file_set, 'extended_config', {})
                temp_folder = extended_config.get('temp_folder', None)
            
            if not temp_folder or not os.path.exists(temp_folder):
                return None
                
            dir_name = os.path.basename(dir_relative_path)
            zip_filename = f"{dir_name}.zip"
            zip_path = os.path.join(temp_folder, zip_filename)
            
            if os.path.exists(zip_path):
                return zip_path
            
            return None
            
        except Exception as e:
            print(f"[ERROR] ZIP ファイル名取得エラー: {e}")
            return None
    
    def _create_zip_file_item_for_directory_and_fileset(self, file_set: FileSet, dir_relative_path: str, zip_path: str) -> FileItem:
        """ファイルセット用のZIPファイル項目作成"""
        try:
            zip_filename = os.path.basename(zip_path)
            zip_item = FileItem(
                path=zip_path,
                relative_path=zip_filename,
                name=zip_filename,
                file_type=FileType.FILE,
                item_type=FileItemType.ATTACHMENT
            )
            
            if os.path.exists(zip_path):
                zip_item.size = os.path.getsize(zip_path)
            
            return zip_item
            
        except Exception as e:
            print(f"[ERROR] ZIP ファイル項目作成エラー: {e}")
            return FileItem(
                path=zip_path or "",
                relative_path=os.path.basename(zip_path) if zip_path else "error.zip",
                name=os.path.basename(zip_path) if zip_path else "error.zip",
                file_type=FileType.FILE,
                item_type=FileItemType.ATTACHMENT
            )
    
    def _get_mapping_file_path_for_fileset(self, file_set: FileSet) -> Optional[str]:
        """ファイルセット用のマッピングファイルパス取得"""
        try:
            temp_folder = getattr(file_set, 'temp_folder', None)
            extended_config = getattr(file_set, 'extended_config', {})
            if not temp_folder and 'temp_folder' in extended_config:
                temp_folder = extended_config['temp_folder']
            
            if temp_folder and os.path.exists(temp_folder):
                mapping_path = os.path.join(temp_folder, "path_mapping.xlsx")
                if os.path.exists(mapping_path):
                    return mapping_path
            
            return None
        except Exception as e:
            print(f"[WARNING] マッピングファイル取得エラー: {e}")
            return None
    
    def _execute_single_upload_for_fileset(self, bearer_token: str, dataset_id: str, file_item: FileItem) -> dict:
        """ファイルセット用の単一ファイルアップロード処理"""
        try:
            if not os.path.exists(file_item.path):
                print(f"[ERROR] ファイルが存在しません: {file_item.path}")
                return {"error": f"ファイルが存在しません: {file_item.path}"}
            
            # 登録ファイル名を取得（重複回避のためフラット化されたファイル名を使用）
            register_filename = self._get_safe_register_filename(file_item)
            encoded_filename = urllib.parse.quote(register_filename)
            
            print(f"[DEBUG] アップロード実行: {register_filename} (元ファイル: {os.path.basename(file_item.path)})")
            print(f"[DEBUG] データセットID: {dataset_id}")
            
            # APIエンドポイント
            url = f"https://rde-entry-api-arim.nims.go.jp/uploads?datasetId={dataset_id}"
            
            # リクエストヘッダー（Authorizationは削除、post_binary内で自動選択）
            headers = {
                "Accept": "application/json",
                "X-File-Name": encoded_filename,
                "User-Agent": "PythonUploader/1.0",
            }
            
            # ファイルサイズ確認
            file_size = os.path.getsize(file_item.path)
            print(f"[DEBUG] ファイルサイズ: {file_size} bytes")
            
            # ファイルを読み込み
            with open(file_item.path, 'rb') as f:
                binary_data = f.read()
            
            print(f"[DEBUG] リクエスト送信 - URL: {url}")
            print(f"[DEBUG] リクエスト送信 - ヘッダー: {headers}")
            
            # Bearer Token自動選択対応のpost_binaryを使用
            from classes.utils.api_request_helper import post_binary
            
            resp = post_binary(url, binary_data, bearer_token=None, headers=headers)
            
            print(f"[DEBUG] レスポンス受信 - ステータス: {resp.status_code if resp else 'None'}")
            if resp:
                print(f"[DEBUG] レスポンス受信 - テキスト: {resp.text[:500]}")
            
            if resp is None or not (200 <= resp.status_code < 300):
                error_text = resp.text[:200] if resp else '通信エラー'
                error_msg = f"HTTP {resp.status_code if resp else 'None'}: {error_text}"
                print(f"[ERROR] アップロード失敗: {error_msg}")
                return {"error": error_msg}
            
            # JSONレスポンスをパース
            try:
                response_data = resp.json()
                upload_id = response_data.get("uploadId")
                
                if not upload_id:
                    error_msg = "レスポンスにuploadIdが含まれていません"
                    print(f"[ERROR] {error_msg}: {response_data}")
                    return {"error": error_msg, "response_data": response_data}
                
                print(f"[DEBUG] アップロード成功: uploadId = {upload_id}")
                return {
                    "upload_id": upload_id,
                    "response_data": response_data,
                    "status_code": resp.status_code
                }
                
            except Exception as json_error:
                error_msg = f"JSONパースエラー: {str(json_error)}"
                print(f"[ERROR] {error_msg}")
                return {"error": error_msg}
            
        except Exception as e:
            error_msg = f"アップロード処理エラー: {str(e)}"
            print(f"[ERROR] {error_msg}")
            import traceback
            traceback.print_exc()
            return {"error": error_msg}
    
    def _get_safe_register_filename(self, file_item: FileItem) -> str:
        """安全な登録ファイル名を取得（重複回避対応）"""
        try:
            # ファイルアイテムから所属するファイルセットを検索
            target_file_set = None
            
            # BatchRegisterPreviewDialogの場合（複数ファイルセット）
            if hasattr(self, 'file_sets'):
                for fs in self.file_sets:
                    if fs and hasattr(fs, 'get_valid_items'):
                        valid_items = fs.get_valid_items()
                        if file_item in valid_items:
                            target_file_set = fs
                            break
            
            # FileSetPreviewWidgetの場合（単一ファイルセット）
            elif hasattr(self, 'file_set'):
                target_file_set = self.file_set
            
            if not target_file_set:
                # ファイルセットが見つからない場合はrelative_pathを使用
                print(f"[DEBUG] ファイルセットが見つからないため、relative_pathを使用: {file_item.relative_path}")
                return file_item.relative_path.replace('/', '__').replace('\\', '__')
            
            organize_method = getattr(target_file_set, 'organize_method', None)
            if organize_method == PathOrganizeMethod.FLATTEN:
                # フラット化の場合は、相対パスをダブルアンダースコアで置き換え
                relative_path = file_item.relative_path.replace('/', '__').replace('\\', '__')
                print(f"[DEBUG] フラット化ファイル名生成: {file_item.relative_path} -> {relative_path}")
                return relative_path
            elif organize_method == PathOrganizeMethod.ZIP:
                # ZIP化の場合は適切なメソッドを呼び出し
                if hasattr(self, '_get_zip_display_filename_for_fileset'):
                    return self._get_zip_display_filename_for_fileset(file_item, target_file_set)
                elif hasattr(self, '_get_zip_display_filename_for_single_fileset'):
                    return self._get_zip_display_filename_for_single_fileset(file_item)
                else:
                    return file_item.name
            else:
                return file_item.relative_path
                
        except Exception as e:
            print(f"[ERROR] _get_safe_register_filename エラー: {e}")
            import traceback
            traceback.print_exc()
            # フォールバック：相対パスベースのユニークファイル名
            fallback_name = file_item.relative_path.replace('/', '__').replace('\\', '__')
            print(f"[DEBUG] フォールバック名を使用: {fallback_name}")
            return fallback_name

    def _build_form_values_from_fileset(self, file_set: FileSet) -> dict:
        """ファイルセット用のフォーム値構築（通常登録との互換性確保）"""
        try:
            form_values = {}
            extended_config = getattr(file_set, 'extended_config', {})
            
            # 基本情報（extended_configを優先）
            form_values['dataName'] = extended_config.get('data_name') or getattr(file_set, 'data_name', '') or f"一括登録_{file_set.name}"
            form_values['basicDescription'] = extended_config.get('description') or getattr(file_set, 'description', '') or "一括登録によるデータ"
            form_values['experimentId'] = extended_config.get('experiment_id') or getattr(file_set, 'experiment_id', '') or ""
            
            # 試料情報の処理
            sample_mode = extended_config.get('sample_mode') or getattr(file_set, 'sample_mode', 'new')
            sample_id_from_config = extended_config.get('sample_id') or getattr(file_set, 'sample_id', '')
            
            # 試料モードによる分岐処理（通常登録と同じ仕様）
            if sample_mode == 'existing' and sample_id_from_config:
                # 既存試料選択の場合：sampleIdを設定
                form_values['sampleId'] = sample_id_from_config
                # 参考値として試料情報も保持（通常登録と同じ構造）
                form_values['sampleNames'] = extended_config.get('sample_name') or getattr(file_set, 'sample_name', '') or f"試料_{file_set.name}"
                form_values['sampleDescription'] = extended_config.get('sample_description') or getattr(file_set, 'sample_description', '') or "一括登録試料"
                form_values['sampleComposition'] = extended_config.get('sample_composition') or getattr(file_set, 'sample_composition', '') or ""
                print(f"[DEBUG] static既存試料ID設定: {sample_id_from_config}")
            else:
                # 新規作成の場合：sampleNamesを設定（通常登録と同じ）
                form_values['sampleNames'] = extended_config.get('sample_name') or getattr(file_set, 'sample_name', '') or f"試料_{file_set.name}"
                form_values['sampleDescription'] = extended_config.get('sample_description') or getattr(file_set, 'sample_description', '') or "一括登録試料"
                form_values['sampleComposition'] = extended_config.get('sample_composition') or getattr(file_set, 'sample_composition', '') or ""
                # 追加の新規試料情報
                form_values['sampleReferenceUrl'] = extended_config.get('reference_url') or getattr(file_set, 'reference_url', '') or ""
                form_values['sampleTags'] = extended_config.get('tags') or getattr(file_set, 'tags', '') or ""
                print(f"[DEBUG] static新規試料情報設定完了: {form_values['sampleNames']}")
            
            # 固有情報（カスタム値）の抽出 - ファイルセット属性とextended_configから
            custom_values = getattr(file_set, 'custom_values', {}) or extended_config.get('custom_values', {})
            
            if not custom_values:
                # custom_valuesが空の場合、extended_configから直接抽出
                custom_values = {}
                exclude_keys = {
                    'data_name', 'description', 'experiment_id', 'reference_url', 'tags',
                    'sample_mode', 'sample_id', 'sample_name', 'sample_description', 
                    'sample_composition', 'dataset_id', 'dataset_name',
                    'temp_folder', 'temp_created', 'mapping_file', 'last_sample_id',
                    'last_sample_name', 'registration_timestamp', 'selected_dataset'
                }
                for key, value in extended_config.items():
                    if key not in exclude_keys and value is not None and value != "":
                        custom_values[key] = value
            
            form_values['custom'] = custom_values
            
            return form_values
            
        except Exception as e:
            print(f"[ERROR] フォーム値構築エラー: {e}")
            return {}
    
    def _build_files_payload_for_fileset(self, file_set: FileSet, uploaded_files: List[FileItem]) -> Tuple[dict, List[dict]]:
        """ファイルセット用のファイルペイロード構築"""
        try:
            dataFiles = {"data": []}
            attachments = []
            mapping_upload_id = getattr(file_set, 'mapping_upload_id', None)
            # 既存の添付ファイルupload_idを記録
            attachment_ids = set()
            for file_item in uploaded_files:
                upload_id = getattr(file_item, 'upload_id', None)
                if not upload_id:
                    continue
                item_type = getattr(file_item, 'item_type', None)
                if item_type == FileItemType.ATTACHMENT:
                    # path_mapping.xlsx 以外も含める
                    attachments.append({
                        "uploadId": upload_id,
                        "description": file_item.name
                    })
                    attachment_ids.add(upload_id)
                else:
                    dataFiles["data"].append({
                        "type": "upload",
                        "id": upload_id
                    })
            # mapping_upload_id があれば必ず添付ファイルに追加（重複排除）
            if mapping_upload_id and mapping_upload_id not in attachment_ids:
                attachments.append({
                    "uploadId": mapping_upload_id,
                    "description": "path_mapping.xlsx"
                })
            return dataFiles, attachments
        except Exception as e:
            print(f"[ERROR] ファイルペイロード構築エラー: {e}")
            return {"data": []}, []
    
    def _is_data_file_extension(self, file_item: FileItem) -> bool:
        """拡張子ベースのデータファイル判定"""
        data_extensions = {'.csv', '.xlsx', '.xls', '.txt', '.dat', '.json', '.xml'}
        extension = getattr(file_item, 'extension', '')
        return extension.lower() in data_extensions if extension else False
    
    def _save_sample_info_to_fileset(self, file_set: FileSet, sample_info: dict):
        """ファイルセット用の試料情報保存"""
        try:
            if not hasattr(file_set, 'extended_config'):
                file_set.extended_config = {}
            
            file_set.extended_config['last_sample_id'] = sample_info['sample_id']
            file_set.extended_config['last_sample_name'] = sample_info.get('sample_name', '')
            file_set.extended_config['registration_timestamp'] = str(datetime.now().isoformat())
            
        except Exception as e:
            print(f"[WARNING] 試料情報保存エラー: {e}")
    
    def _extract_sample_info_from_response(self, response_data: dict) -> Optional[dict]:
        """レスポンスから試料情報を抽出"""
        try:
            data = response_data.get('data', {})
            relationships = data.get('relationships', {})
            sample_data = relationships.get('sample', {}).get('data', {})
            
            if sample_data and sample_data.get('id'):
                return {
                    'sample_id': sample_data['id'],
                    'sample_name': f"Sample_{sample_data['id'][:8]}"
                }
            
            return None
            
        except Exception as e:
            print(f"[WARNING] 試料情報抽出エラー: {e}")
            return None
    
    def _format_size(self, size_bytes: int) -> str:
        """ファイルサイズを人間が読みやすい形式に変換"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        size = float(size_bytes)
        while size >= 1024 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.1f} {size_names[i]}"
    
    def get_validated_file_sets(self) -> List[FileSet]:
        """検証済みファイルセットを取得（重複ファイル除外後）"""
        return self.file_sets

    def _batch_register_all_filesets_without_confirmation(self):
        """確認ダイアログなしで全ファイルセット一括データ登録"""
        try:
            print("[INFO] 確認ダイアログなしで全ファイルセット一括データ登録開始")
            self._batch_register_all()
        except Exception as e:
            print(f"[ERROR] 全ファイルセット一括データ登録処理でエラー: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "エラー", f"全ファイルセット一括データ登録処理でエラーが発生しました:\n{str(e)}")
