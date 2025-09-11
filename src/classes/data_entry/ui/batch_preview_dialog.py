"""
一括登録プレビューダイアログ

ファイルセットごとの詳細情報、ファイル一覧、設定情報を表示
"""

import os
import urllib.parse
from typing import List, Dict, Optional, Set
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget, 
    QTableWidgetItem, QLabel, QPushButton, QTextEdit, QGroupBox,
    QHeaderView, QScrollArea, QWidget, QSplitter, QMessageBox,
    QDialogButtonBox, QComboBox, QProgressDialog
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QFont, QColor

from classes.data_entry.core.file_set_manager import FileSet, FileItem, FileType, PathOrganizeMethod


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
        
        temp_folder_layout.addWidget(self.open_temp_folder_button)
        temp_folder_layout.addWidget(self.open_mapping_file_button)
        temp_folder_layout.addStretch()
        
        settings_layout.addLayout(temp_folder_layout)
        
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
        """ファイル一覧テーブルを読み込み"""
        try:
            valid_items = self.file_set.get_valid_items()
            file_items = [item for item in valid_items if item.file_type == FileType.FILE]
            
            self.files_table.setRowCount(len(file_items))
            
            for row, file_item in enumerate(file_items):
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
                file_type_combo.addItems(["データファイル", "添付ファイル"])
                
                # 現在の設定を反映（フラット化の場合は初期値をデータファイルに）
                current_type = self._get_file_type_category(file_item)
                if current_type == "データファイル":
                    file_type_combo.setCurrentIndex(0)
                else:
                    file_type_combo.setCurrentIndex(1)
                
                # フラット化の場合は初期値をデータファイルに設定
                if (self.file_set.organize_method == PathOrganizeMethod.FLATTEN and 
                    not hasattr(file_item, '_file_category')):
                    file_type_combo.setCurrentIndex(0)
                
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
            sample_mode = getattr(self.file_set, 'sample_mode', 'new')
            sample_info.append(f"  モード: {self._get_sample_mode_display()}")
            
            # 拡張設定から試料情報を補完
            extended_config = getattr(self.file_set, 'extended_config', {})
            
            if sample_mode == 'existing' or extended_config.get('sample_mode') == '既存試料使用':
                sample_id = getattr(self.file_set, 'sample_id', None) or extended_config.get('sample_id', None)
                sample_info.append(f"  既存試料ID: {sample_id or '未設定'}")
            else:
                sample_name = getattr(self.file_set, 'sample_name', None) or extended_config.get('sample_name', None)
                sample_description = getattr(self.file_set, 'sample_description', None) or extended_config.get('sample_description', None)
                sample_composition = getattr(self.file_set, 'sample_composition', None) or extended_config.get('sample_composition', None)
                sample_info.append(f"  試料名: {sample_name or '未設定'}")
                sample_info.append(f"  試料説明: {sample_description or '未設定'}")
                sample_info.append(f"  組成: {sample_composition or '未設定'}")
            
            # 固有情報の詳細取得
            custom_values = getattr(self.file_set, 'custom_values', {})
            
            # デバッグ情報を出力
            print(f"[DEBUG] プレビュー - ファイルセット属性custom_values: {custom_values}")
            
            # カスタム値が空の場合、拡張設定から取得を試行
            if not custom_values:
                extended_config = getattr(self.file_set, 'extended_config', {})
                print(f"[DEBUG] プレビュー - extended_config全体: {extended_config}")
                
                # 拡張設定内のカスタム値やインボイススキーマ関連の値を抽出
                custom_candidates = {}
                for key, value in extended_config.items():
                    # 基本フィールド以外をカスタム値として扱う
                    basic_fields = {'description', 'experiment_id', 'reference_url', 'tags', 
                                  'sample_mode', 'sample_id', 'sample_name', 'sample_description', 
                                  'sample_composition', 'temp_folder', 'mapping_file', 'temp_created'}
                    if key not in basic_fields and value:
                        custom_candidates[key] = value
                        print(f"[DEBUG] プレビュー - カスタム値候補: {key} = {value}")
                custom_values = custom_candidates
            
            custom_info = []
            if custom_values:
                custom_info.append(f"  カスタム値: {len(custom_values)}個設定済み")
                for key, value in custom_values.items():
                    custom_info.append(f"    {key}: {value}")
            else:
                custom_info.append("  設定項目なし")
            
            # 一時フォルダ情報を取得
            temp_folder = getattr(self.file_set, 'temp_folder', None)
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
                if mapping_file and os.path.exists(mapping_file):
                    temp_info.append(f"  マッピングファイル: {mapping_file}")
                else:
                    temp_info.append(f"  マッピングファイル: 存在しません")
                temp_info.append(f"  整理方法: {self._get_organize_method_display()}")
            else:
                temp_info.append("  一時フォルダ未作成")
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
    
    def _get_register_filename(self, file_item: FileItem) -> str:
        """登録時のファイル名を取得（フラット化対応）"""
        try:
            if self.file_set.organize_method == PathOrganizeMethod.FLATTEN:
                # フラット化の場合は、相対パスをダブルアンダースコアで置き換え
                relative_path = file_item.relative_path.replace('/', '__').replace('\\', '__')
                return relative_path
            elif self.file_set.organize_method == PathOrganizeMethod.ZIP:
                # ZIP化の場合は、最上位レベルのファイルは直接、それ以外はZIP内パス
                relative_path = Path(file_item.relative_path)
                if len(relative_path.parts) == 1:
                    # 直接ファイル
                    return file_item.name
                else:
                    # ZIP内ファイル
                    zip_name = f"{relative_path.parts[0]}.zip"
                    return f"{zip_name} (ZIP内: {'/'.join(relative_path.parts[1:])})"
            else:
                return file_item.relative_path
        except:
            return file_item.name or "不明なファイル"
    
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
            # ファイルアイテムに種別を設定
            setattr(file_item, '_file_category', text)
            print(f"[DEBUG] ファイル種別変更: {file_item.name} → {text}")
            
            # マッピングファイルを再作成
            self._recreate_mapping_file()
            
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
            
            # マッピングファイルボタンの有効/無効
            if mapping_file and os.path.exists(mapping_file):
                self.open_mapping_file_button.setEnabled(True)
                self.open_mapping_file_button.setText("マッピングファイルを開く")
            else:
                self.open_mapping_file_button.setEnabled(False)
                self.open_mapping_file_button.setText("マッピングファイルなし")
                
        except Exception as e:
            print(f"[WARNING] ボタン状態更新エラー: {e}")
            self.open_temp_folder_button.setEnabled(False)
            self.open_mapping_file_button.setEnabled(False)
    
    def _get_sample_mode_display(self) -> str:
        """試料モードの表示名を取得"""
        try:
            # 直接の属性から取得を試行
            sample_mode = getattr(self.file_set, 'sample_mode', None)
            
            # 属性にない場合は拡張設定から取得
            if not sample_mode:
                extended_config = getattr(self.file_set, 'extended_config', {})
                sample_mode_text = extended_config.get('sample_mode', '新規作成')
                
                # テキストベースで判定
                if sample_mode_text == "既存試料使用":
                    return "既存試料使用"
                elif sample_mode_text == "前回と同じ":
                    return "前回と同じ"
                else:
                    return "新規作成"
            
            # 属性ベースの変換
            mode_map = {
                "new": "新規作成",
                "existing": "既存試料使用",
                "same_as_previous": "前回と同じ"
            }
            return mode_map.get(sample_mode, sample_mode)
        except:
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
                
            # Bearerトークンを取得（親から継承またはファイルから読み取り）
            bearer_token = self.bearer_token
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
                QMessageBox.warning(self, "エラー", "認証トークンが取得できません。ログインしてください。")
                return
            
            # トークンの形式をチェック・清浄化
            bearer_token = bearer_token.strip()
            
            # デバッグ：トークンの内容確認
            print(f"[DEBUG] トークン処理前: 長さ={len(bearer_token)}, 先頭20文字={repr(bearer_token[:20])}")
            
            # 様々なプレフィックスを除去
            if bearer_token.startswith('BearerToken='):
                bearer_token = bearer_token[12:]  # 'BearerToken='プレフィックスを除去
                print(f"[DEBUG] BearerToken=プレフィックス除去後: 長さ={len(bearer_token)}")
            elif bearer_token.startswith('Bearer '):
                bearer_token = bearer_token[7:]  # 'Bearer 'プレフィックスを除去
                print(f"[DEBUG] Bearer プレフィックス除去後: 長さ={len(bearer_token)}")
            
            # トークンがJWT形式かどうか確認（eyJ で始まる）
            if not bearer_token.startswith('eyJ'):
                print(f"[WARNING] トークンがJWT形式ではないようです: {bearer_token[:20]}...")
            
            print(f"[DEBUG] 最終トークン: 長さ={len(bearer_token)}, 先頭10文字={bearer_token[:10]}, 末尾10文字={bearer_token[-10:]}")
            
            # ファイル情報を取得
            filename = os.path.basename(file_item.path)
            encoded_filename = urllib.parse.quote(filename)
            file_size = os.path.getsize(file_item.path)
            
            # APIエンドポイントとヘッダー情報を準備（既存実装と完全一致）
            url = f"https://rde-entry-api-arim.nims.go.jp/uploads?datasetId={dataset_id}"
            headers = {
                "Authorization": f"Bearer {bearer_token}",
                "Accept": "application/json",
                "Content-Type": "application/octet-stream",
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
  トークン長: {len(bearer_token)} 文字
  トークン先頭: {bearer_token[:15]}...
  トークン末尾: ...{bearer_token[-15:]}
  
リクエストヘッダー:
  Authorization: Bearer {bearer_token[:10]}...{bearer_token[-10:]}
  Accept: {headers["Accept"]}
  Content-Type: {headers["Content-Type"]}
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
                # 改良されたアップロード処理を実行
                upload_result = self._execute_upload_with_debug(
                    bearer_token, dataset_id, file_item.path, headers, url
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
    
    def _execute_upload_with_debug(self, bearer_token, dataset_id, file_path, headers, url):
        """デバッグ機能付きアップロード実行（既存実装準拠）"""
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
            
            # 既存実装と完全に一致するヘッダーを使用（5つのみ）
            actual_headers = {
                "Authorization": f"Bearer {bearer_token}",
                "Accept": "application/json",
                "Content-Type": "application/octet-stream",
                "X-File-Name": encoded_filename,
                "User-Agent": "PythonUploader/1.0",
            }
            
            print(f"[DEBUG] API呼び出し開始: POST {url}")
            print(f"[DEBUG] リクエストヘッダー数: {len(actual_headers)}")
            print(f"[DEBUG] Content-Type: {actual_headers['Content-Type']}")
            print(f"[DEBUG] X-File-Name: {actual_headers['X-File-Name']}")
            print(f"[DEBUG] バイナリデータサイズ: {len(binary_data)} bytes")
            print(f"[DEBUG] Authorization: Bearer {bearer_token[:10]}...{bearer_token[-10:]}")
            # print(f"[DEBUG] Accept: {actual_headers}")
            # HTTP通信ヘルパーを使用
            from classes.utils.api_request_helper import post_binary
            
            resp = post_binary(url, binary_data, headers=actual_headers, bearer_token=bearer_token)
            
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


class BatchRegisterPreviewDialog(QDialog):
    """一括登録プレビューダイアログ"""
    
    def __init__(self, file_sets: List[FileSet], parent=None, bearer_token: str = None):
        super().__init__(parent)
        self.file_sets = file_sets
        self.duplicate_files = set()
        self.bearer_token = bearer_token
        self.setWindowTitle("一括登録プレビュー")
        self.setModal(True)
        self.resize(1000, 700)
        
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
