"""
マスタデータ管理タブ

ARIMデータポータルサイトからマスタデータ（マテリアルインデックス・タグ）を
取得・表示・管理するためのタブウィジェット
"""

import sys
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QComboBox,
    QMessageBox, QProgressDialog, QHeaderView, QLineEdit,
    QApplication
)
from qt_compat.core import Qt, Signal

from classes.managers.log_manager import get_logger
from ..core.master_data import MasterDataManager

logger = get_logger("DataPortal.MasterTab")


class MasterDataTab(QWidget):
    """
    マスタデータ管理タブ
    
    機能:
    - 環境選択（テスト/本番）
    - マテリアルインデックスマスタの取得・表示
    - タグマスタの取得・表示
    - マスタデータの保存・読み込み
    """
    
    # シグナル定義
    master_fetched = Signal(str, bool)  # マスタタイプ, 成功フラグ
    
    def __init__(self, parent=None):
        """初期化"""
        super().__init__(parent)
        
        self.master_manager = None
        self.current_environment = "production"
        
        # フィルタリング用のデータ保持
        self.material_index_full_data = {}
        self.tag_full_data = {}
        self.equipment_full_data = {}  # 設備分類
        
        self._init_ui()
        logger.info("マスタデータタブ初期化完了")
    
    def _init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        
        # 環境選択グループ
        env_group = self._create_environment_group()
        layout.addWidget(env_group)
        
        # マテリアルインデックスマスタグループ
        material_group = self._create_material_index_group()
        layout.addWidget(material_group)
        
        # タグマスタグループ
        tag_group = self._create_tag_group()
        layout.addWidget(tag_group)
        
        # 設備分類マスタグループ
        equipment_group = self._create_equipment_group()
        layout.addWidget(equipment_group)
        
        layout.addStretch()
    
    def _create_environment_group(self) -> QGroupBox:
        """環境選択グループを作成"""
        group = QGroupBox("環境選択")
        layout = QHBoxLayout(group)
        
        layout.addWidget(QLabel("対象環境:"))
        
        self.env_combo = QComboBox()
        self.env_combo.addItem("本番環境", "production")
        self.env_combo.addItem("テスト環境", "test")
        self.env_combo.currentIndexChanged.connect(self._on_environment_changed)
        layout.addWidget(self.env_combo)
        
        self.env_status_label = QLabel("✅ 本番環境")
        layout.addWidget(self.env_status_label)
        
        layout.addStretch()
        
        return group
    
    def _create_material_index_group(self) -> QGroupBox:
        """マテリアルインデックスマスタグループを作成"""
        group = QGroupBox("📋 マテリアルインデックスマスタ")
        layout = QVBoxLayout(group)
        
        # ボタン行
        button_layout = QHBoxLayout()
        
        self.material_fetch_btn = QPushButton("🔄 取得")
        self.material_fetch_btn.clicked.connect(self._on_fetch_material_index)
        button_layout.addWidget(self.material_fetch_btn)
        
        self.material_save_btn = QPushButton("💾 保存")
        self.material_save_btn.clicked.connect(self._on_save_material_index)
        self.material_save_btn.setEnabled(False)
        button_layout.addWidget(self.material_save_btn)
        
        self.material_load_btn = QPushButton("📂 読み込み")
        self.material_load_btn.clicked.connect(self._on_load_material_index)
        button_layout.addWidget(self.material_load_btn)
        
        self.material_open_folder_btn = QPushButton("📁 フォルダを開く")
        self.material_open_folder_btn.clicked.connect(self._on_open_master_folder)
        button_layout.addWidget(self.material_open_folder_btn)
        
        self.material_info_label = QLabel("未取得")
        button_layout.addWidget(self.material_info_label)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # フィルタ行
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("🔍 フィルタ:"))
        
        self.material_filter_input = QLineEdit()
        self.material_filter_input.setPlaceholderText("マテリアルインデックス名で検索...")
        self.material_filter_input.textChanged.connect(self._on_material_filter_changed)
        filter_layout.addWidget(self.material_filter_input)
        
        layout.addLayout(filter_layout)
        
        # テーブル
        self.material_table = QTableWidget()
        self.material_table.setColumnCount(2)
        self.material_table.setHorizontalHeaderLabels(["コード", "マテリアルインデックス名"])
        self.material_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.material_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.material_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.material_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.material_table.setMaximumHeight(300)
        layout.addWidget(self.material_table)
        
        return group
    
    def _create_tag_group(self) -> QGroupBox:
        """タグマスタグループを作成"""
        group = QGroupBox("🏷️ タグマスタ")
        layout = QVBoxLayout(group)
        
        # ボタン行
        button_layout = QHBoxLayout()
        
        self.tag_fetch_btn = QPushButton("🔄 取得")
        self.tag_fetch_btn.clicked.connect(self._on_fetch_tag)
        button_layout.addWidget(self.tag_fetch_btn)
        
        self.tag_save_btn = QPushButton("💾 保存")
        self.tag_save_btn.clicked.connect(self._on_save_tag)
        self.tag_save_btn.setEnabled(False)
        button_layout.addWidget(self.tag_save_btn)
        
        self.tag_load_btn = QPushButton("📂 読み込み")
        self.tag_load_btn.clicked.connect(self._on_load_tag)
        button_layout.addWidget(self.tag_load_btn)
        
        self.tag_open_folder_btn = QPushButton("📁 フォルダを開く")
        self.tag_open_folder_btn.clicked.connect(self._on_open_master_folder)
        button_layout.addWidget(self.tag_open_folder_btn)
        
        self.tag_info_label = QLabel("未取得")
        button_layout.addWidget(self.tag_info_label)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # フィルタ行
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("🔍 フィルタ:"))
        
        self.tag_filter_input = QLineEdit()
        self.tag_filter_input.setPlaceholderText("タグ名で検索...")
        self.tag_filter_input.textChanged.connect(self._on_tag_filter_changed)
        filter_layout.addWidget(self.tag_filter_input)
        
        layout.addLayout(filter_layout)
        
        # テーブル
        self.tag_table = QTableWidget()
        self.tag_table.setColumnCount(2)
        self.tag_table.setHorizontalHeaderLabels(["コード", "タグ名"])
        self.tag_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tag_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tag_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tag_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tag_table.setMaximumHeight(300)
        layout.addWidget(self.tag_table)
        
        return group
    
    def _create_equipment_group(self) -> QGroupBox:
        """設備分類マスタグループを作成"""
        group = QGroupBox("⚙️ 設備分類マスタ")
        layout = QVBoxLayout(group)
        
        # ボタン行
        button_layout = QHBoxLayout()
        
        self.equipment_fetch_btn = QPushButton("🔄 取得")
        self.equipment_fetch_btn.clicked.connect(self._on_fetch_equipment)
        button_layout.addWidget(self.equipment_fetch_btn)
        
        self.equipment_load_btn = QPushButton("📂 読み込み")
        self.equipment_load_btn.clicked.connect(self._on_load_equipment)
        button_layout.addWidget(self.equipment_load_btn)
        
        self.equipment_open_folder_btn = QPushButton("📁 フォルダを開く")
        self.equipment_open_folder_btn.clicked.connect(self._on_open_master_folder)
        button_layout.addWidget(self.equipment_open_folder_btn)
        
        self.equipment_info_label = QLabel("未取得")
        button_layout.addWidget(self.equipment_info_label)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # フィルタ行
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("🔍 フィルタ:"))
        
        self.equipment_filter_input = QLineEdit()
        self.equipment_filter_input.setPlaceholderText("設備分類名で検索...")
        self.equipment_filter_input.textChanged.connect(self._on_equipment_filter_changed)
        filter_layout.addWidget(self.equipment_filter_input)
        
        layout.addLayout(filter_layout)
        
        # テーブル
        self.equipment_table = QTableWidget()
        self.equipment_table.setColumnCount(2)
        self.equipment_table.setHorizontalHeaderLabels(["コード", "設備分類名"])
        self.equipment_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.equipment_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.equipment_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.equipment_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.equipment_table.setMaximumHeight(300)
        layout.addWidget(self.equipment_table)
        
        return group
    
    def set_portal_client(self, portal_client):
        """
        PortalClientを設定
        
        Args:
            portal_client: PortalClientインスタンス
        """
        if portal_client:
            self.master_manager = MasterDataManager(portal_client)
            self.current_environment = portal_client.environment
            
            # 環境選択を更新
            index = 0 if self.current_environment == "production" else 1
            self.env_combo.setCurrentIndex(index)
            
            # 既存のマスタ情報を更新
            self._update_master_info()
            
            # 保存済みデータを自動読み込み
            self._auto_load_saved_data()
            
            logger.info(f"PortalClient設定完了: {self.current_environment}")
    
    def _on_environment_changed(self, index: int):
        """環境変更時の処理"""
        env_data = self.env_combo.itemData(index)
        self.current_environment = env_data
        
        env_name = "本番環境" if env_data == "production" else "テスト環境"
        self.env_status_label.setText(f"✅ {env_name}")
        
        # マスタマネージャを再作成（環境が変わったら）
        if self.master_manager:
            from ..core.portal_client import PortalClient
            new_client = PortalClient(environment=self.current_environment)
            # 既存の認証情報をコピー
            if self.master_manager.client.credentials:
                new_client.set_credentials(self.master_manager.client.credentials)
            self.master_manager = MasterDataManager(new_client)
            
            # 既存のマスタ情報を更新
            self._update_master_info()
            
            # 保存済みデータを自動読み込み
            self._auto_load_saved_data()
        
        logger.info(f"環境変更: {env_name}")
    
    def _update_master_info(self):
        """マスタ情報を更新"""
        if not self.master_manager:
            return
        
        # マテリアルインデックス
        material_info = self.master_manager.get_master_info("material_index")
        if material_info["exists"]:
            self.material_info_label.setText(
                f"保存済み: {material_info['count']} 件 "
                f"(取得: {material_info['fetched_at'][:10]})"
            )
        else:
            self.material_info_label.setText("未保存")
        
        # タグ
        tag_info = self.master_manager.get_master_info("tag")
        if tag_info["exists"]:
            self.tag_info_label.setText(
                f"保存済み: {tag_info['count']} 件 "
                f"(取得: {tag_info['fetched_at'][:10]})"
            )
        else:
            self.tag_info_label.setText("未保存")
        
        # 設備分類
        success, equipment_data = self.master_manager.load_equipment_master()
        if success and equipment_data:
            self.equipment_info_label.setText(f"キャッシュ済み: {len(equipment_data)} 件")
        else:
            self.equipment_info_label.setText("未キャッシュ")
    
    def _on_fetch_material_index(self):
        """マテリアルインデックスマスタ取得"""
        if not self.master_manager:
            # PortalClientが未設定の場合、自動接続を試行
            success = self._try_auto_connect()
            if not success:
                QMessageBox.warning(self, "エラー", "ログイン設定タブで接続テストを実行してください")
                return
        
        # プログレスダイアログ表示
        progress = QProgressDialog("マテリアルインデックスマスタを取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        
        try:
            # マスタ取得
            success, data = self.master_manager.fetch_material_index_master()
            
            progress.close()
            
            if success and data:
                # テーブルに表示
                self._display_material_index_data(data)
                self.material_save_btn.setEnabled(True)
                self.material_info_label.setText(f"✅ 取得完了: {len(data)} 件")
                
                # 既存ファイルがない場合は自動保存
                material_info = self.master_manager.get_master_info("material_index")
                if not material_info["exists"]:
                    logger.info("既存ファイルがないため自動保存を実行します")
                    save_success = self.master_manager.save_material_index_master(data)
                    if save_success:
                        logger.info("マテリアルインデックスマスタを自動保存しました")
                        self._update_master_info()
                
                QMessageBox.information(
                    self,
                    "取得成功",
                    f"マテリアルインデックスマスタを取得しました\n件数: {len(data)}"
                )
                
                self.master_fetched.emit("material_index", True)
            else:
                QMessageBox.warning(
                    self,
                    "取得失敗",
                    "マテリアルインデックスマスタの取得に失敗しました"
                )
                self.master_fetched.emit("material_index", False)
        
        except Exception as e:
            progress.close()
            logger.error(f"マテリアルインデックスマスタ取得エラー: {e}")
            QMessageBox.critical(
                self,
                "エラー",
                f"マテリアルインデックスマスタ取得中にエラーが発生しました\n{e}"
            )
            self.master_fetched.emit("material_index", False)
    
    def _on_save_material_index(self):
        """マテリアルインデックスマスタ保存"""
        if not self.master_manager:
            return
        
        # テーブルからデータを取得
        data = {}
        for row in range(self.material_table.rowCount()):
            code = self.material_table.item(row, 0).text()
            name = self.material_table.item(row, 1).text()
            data[code] = name
        
        if not data:
            QMessageBox.warning(self, "エラー", "保存するデータがありません")
            return
        
        # 保存
        success = self.master_manager.save_material_index_master(data)
        
        if success:
            QMessageBox.information(
                self,
                "保存成功",
                f"マテリアルインデックスマスタを保存しました\n件数: {len(data)}"
            )
            self._update_master_info()
        else:
            QMessageBox.warning(
                self,
                "保存失敗",
                "マテリアルインデックスマスタの保存に失敗しました"
            )
    
    def _on_load_material_index(self):
        """マテリアルインデックスマスタ読み込み"""
        if not self.master_manager:
            # マスタマネージャがない場合は仮作成
            from ..core.portal_client import PortalClient
            temp_client = PortalClient(environment=self.current_environment)
            from ..core.master_data import MasterDataManager
            self.master_manager = MasterDataManager(temp_client)
        
        success, data = self.master_manager.load_material_index_master()
        
        if success and data:
            self._display_material_index_data(data)
            self.material_save_btn.setEnabled(True)
            QMessageBox.information(
                self,
                "読み込み成功",
                f"マテリアルインデックスマスタを読み込みました\n件数: {len(data)}"
            )
        else:
            QMessageBox.warning(
                self,
                "読み込み失敗",
                "マテリアルインデックスマスタの読み込みに失敗しました\n"
                "ファイルが存在しないか、読み込みエラーが発生しました"
            )
    
    def _display_material_index_data(self, data: dict):
        """マテリアルインデックスデータをテーブルに表示"""
        # フルデータを保持（フィルタリング用）
        self.material_index_full_data = data.copy()
        
        # テーブルをクリアして全データを表示
        self.material_table.setRowCount(0)
        
        for code, name in sorted(data.items()):
            row = self.material_table.rowCount()
            self.material_table.insertRow(row)
            
            self.material_table.setItem(row, 0, QTableWidgetItem(code))
            self.material_table.setItem(row, 1, QTableWidgetItem(name))
        
        logger.info(f"マテリアルインデックスデータ表示: {len(data)} 件")
    
    def _on_fetch_tag(self):
        """タグマスタ取得"""
        if not self.master_manager:
            # PortalClientが未設定の場合、自動接続を試行
            success = self._try_auto_connect()
            if not success:
                QMessageBox.warning(self, "エラー", "ログイン設定タブで接続テストを実行してください")
                return
        
        # プログレスダイアログ表示
        progress = QProgressDialog("タグマスタを取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        
        try:
            # マスタ取得
            success, data = self.master_manager.fetch_tag_master()
            
            progress.close()
            
            if success and data:
                # テーブルに表示
                self._display_tag_data(data)
                self.tag_save_btn.setEnabled(True)
                self.tag_info_label.setText(f"✅ 取得完了: {len(data)} 件")
                
                # 既存ファイルがない場合は自動保存
                tag_info = self.master_manager.get_master_info("tag")
                if not tag_info["exists"]:
                    logger.info("既存ファイルがないため自動保存を実行します")
                    save_success = self.master_manager.save_tag_master(data)
                    if save_success:
                        logger.info("タグマスタを自動保存しました")
                        self._update_master_info()
                
                QMessageBox.information(
                    self,
                    "取得成功",
                    f"タグマスタを取得しました\n件数: {len(data)}"
                )
                
                self.master_fetched.emit("tag", True)
            else:
                QMessageBox.warning(
                    self,
                    "取得失敗",
                    "タグマスタの取得に失敗しました"
                )
                self.master_fetched.emit("tag", False)
        
        except Exception as e:
            progress.close()
            logger.error(f"タグマスタ取得エラー: {e}")
            QMessageBox.critical(
                self,
                "エラー",
                f"タグマスタ取得中にエラーが発生しました\n{e}"
            )
            self.master_fetched.emit("tag", False)
    
    def _on_save_tag(self):
        """タグマスタ保存"""
        if not self.master_manager:
            return
        
        # テーブルからデータを取得
        data = {}
        for row in range(self.tag_table.rowCount()):
            code = self.tag_table.item(row, 0).text()
            name = self.tag_table.item(row, 1).text()
            data[code] = name
        
        if not data:
            QMessageBox.warning(self, "エラー", "保存するデータがありません")
            return
        
        # 保存
        success = self.master_manager.save_tag_master(data)
        
        if success:
            QMessageBox.information(
                self,
                "保存成功",
                f"タグマスタを保存しました\n件数: {len(data)}"
            )
            self._update_master_info()
        else:
            QMessageBox.warning(
                self,
                "保存失敗",
                "タグマスタの保存に失敗しました"
            )
    
    def _on_load_tag(self):
        """タグマスタ読み込み"""
        if not self.master_manager:
            # マスタマネージャがない場合は仮作成
            from ..core.portal_client import PortalClient
            temp_client = PortalClient(environment=self.current_environment)
            from ..core.master_data import MasterDataManager
            self.master_manager = MasterDataManager(temp_client)
        
        success, data = self.master_manager.load_tag_master()
        
        if success and data:
            self._display_tag_data(data)
            self.tag_save_btn.setEnabled(True)
            QMessageBox.information(
                self,
                "読み込み成功",
                f"タグマスタを読み込みました\n件数: {len(data)}"
            )
        else:
            QMessageBox.warning(
                self,
                "読み込み失敗",
                "タグマスタの読み込みに失敗しました\n"
                "ファイルが存在しないか、読み込みエラーが発生しました"
            )
    
    def _display_tag_data(self, data: dict):
        """タグデータをテーブルに表示"""
        # フルデータを保持（フィルタリング用）
        self.tag_full_data = data.copy()
        
        # テーブルをクリアして全データを表示
        self.tag_table.setRowCount(0)
        
        for code, name in sorted(data.items()):
            row = self.tag_table.rowCount()
            self.tag_table.insertRow(row)
            
            self.tag_table.setItem(row, 0, QTableWidgetItem(code))
            self.tag_table.setItem(row, 1, QTableWidgetItem(name))
        
        logger.info(f"タグデータ表示: {len(data)} 件")
    
    def _try_auto_connect(self) -> bool:
        """
        自動接続を試行
        
        Returns:
            bool: 接続成功フラグ
        """
        try:
            logger.info("自動接続を試行中...")
            
            # 親ウィジェットからログイン設定タブを取得
            parent_widget = self.parent()
            if not hasattr(parent_widget, 'login_settings_tab'):
                logger.warning("ログイン設定タブが見つかりません")
                return False
            
            login_tab = parent_widget.login_settings_tab
            
            # PortalClientが既に存在する場合は使用
            if hasattr(login_tab, 'portal_client') and login_tab.portal_client:
                self.set_portal_client(login_tab.portal_client)
                logger.info("既存のPortalClientを使用しました")
                return True
            
            logger.warning("PortalClientが存在しません")
            return False
            
        except Exception as e:
            logger.error(f"自動接続エラー: {e}")
            return False
    
    def _auto_load_saved_data(self):
        """保存済みデータを自動読み込み"""
        if not self.master_manager:
            return
        
        # マテリアルインデックスマスタ
        success, data = self.master_manager.load_material_index_master()
        if success and data:
            self._display_material_index_data(data)
            self.material_save_btn.setEnabled(True)
            logger.info(f"マテリアルインデックスマスタ自動読み込み: {len(data)} 件")
        
        # タグマスタ
        success, data = self.master_manager.load_tag_master()
        if success and data:
            self._display_tag_data(data)
            self.tag_save_btn.setEnabled(True)
            logger.info(f"タグマスタ自動読み込み: {len(data)} 件")
        
        # 設備分類マスタ
        success, data = self.master_manager.load_equipment_master()
        if success and data:
            self._display_equipment_data(data)
            logger.info(f"設備分類マスタ自動読み込み: {len(data)} 件")
    
    def _on_open_master_folder(self):
        """保存先フォルダを開く"""
        try:
            from config.common import get_dynamic_file_path
            import os
            import subprocess
            
            master_dir = get_dynamic_file_path("input/master_data")
            
            # ディレクトリが存在しない場合は作成
            if not os.path.exists(master_dir):
                os.makedirs(master_dir, exist_ok=True)
            
            # エクスプローラーで開く
            if os.name == 'nt':  # Windows
                os.startfile(master_dir)
            elif os.name == 'posix':  # macOS/Linux
                subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', master_dir])
            
            logger.info(f"マスタデータフォルダを開きました: {master_dir}")
            
        except Exception as e:
            logger.error(f"フォルダを開く際にエラー: {e}")
            QMessageBox.warning(
                self,
                "エラー",
                f"フォルダを開けませんでした\n{e}"
            )
    
    def _on_material_filter_changed(self, text: str):
        """マテリアルインデックスフィルタ変更時の処理"""
        filter_text = text.strip().lower()
        
        # フィルタが空の場合は全データを表示
        if not filter_text:
            self._display_material_index_data(self.material_index_full_data)
            return
        
        # フィルタリング実行
        filtered_data = {
            code: name 
            for code, name in self.material_index_full_data.items()
            if filter_text in name.lower()
        }
        
        # テーブルをクリア
        self.material_table.setRowCount(0)
        
        # フィルタ結果を表示
        for code, name in sorted(filtered_data.items()):
            row = self.material_table.rowCount()
            self.material_table.insertRow(row)
            
            self.material_table.setItem(row, 0, QTableWidgetItem(code))
            self.material_table.setItem(row, 1, QTableWidgetItem(name))
        
        logger.debug(f"マテリアルインデックスフィルタ: {len(filtered_data)}/{len(self.material_index_full_data)} 件表示")
    
    def _on_tag_filter_changed(self, text: str):
        """タグフィルタ変更時の処理"""
        filter_text = text.strip().lower()
        
        # フィルタが空の場合は全データを表示
        if not filter_text:
            self._display_tag_data(self.tag_full_data)
            return
        
        # フィルタリング実行
        filtered_data = {
            code: name 
            for code, name in self.tag_full_data.items()
            if filter_text in name.lower()
        }
        
        # テーブルをクリア
        self.tag_table.setRowCount(0)
        
        # フィルタ結果を表示
        for code, name in sorted(filtered_data.items()):
            row = self.tag_table.rowCount()
            self.tag_table.insertRow(row)
            
            self.tag_table.setItem(row, 0, QTableWidgetItem(code))
            self.tag_table.setItem(row, 1, QTableWidgetItem(name))
        
        logger.debug(f"タグフィルタ: {len(filtered_data)}/{len(self.tag_full_data)} 件表示")
    
    def _on_fetch_equipment(self):
        """設備分類マスタ取得"""
        if not self.master_manager:
            QMessageBox.warning(self, "エラー", "ポータルクライアントが設定されていません")
            return
        
        try:
            # プログレスダイアログ表示
            progress = QProgressDialog("設備分類マスタを取得中...", None, 0, 0, self)
            progress.setWindowTitle("取得中")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()
            
            QApplication.processEvents()
            
            # 取得実行
            success, data = self.master_manager.fetch_equipment_master_from_edit_page()
            
            progress.close()
            
            if success and data:
                # テーブルに表示
                self._display_equipment_data(data)
                self.equipment_info_label.setText(f"✅ 取得完了: {len(data)} 件")
                
                QMessageBox.information(
                    self,
                    "取得成功",
                    f"設備分類マスタを取得しました\n件数: {len(data)}\n\nデータは自動的にキャッシュされました"
                )
                
                self.master_fetched.emit("equipment", True)
            else:
                QMessageBox.warning(
                    self,
                    "取得失敗",
                    "設備分類マスタの取得に失敗しました\n\n編集ページにアクセスできるか確認してください"
                )
                self.master_fetched.emit("equipment", False)
        
        except Exception as e:
            progress.close()
            logger.error(f"設備分類マスタ取得エラー: {e}")
            QMessageBox.critical(
                self,
                "エラー",
                f"設備分類マスタ取得中にエラーが発生しました\n{e}"
            )
            self.master_fetched.emit("equipment", False)
    
    def _on_load_equipment(self):
        """設備分類マスタ読み込み"""
        if not self.master_manager:
            # マスタマネージャがない場合は仮作成
            from ..core.portal_client import PortalClient
            temp_client = PortalClient(environment=self.current_environment)
            from ..core.master_data import MasterDataManager
            self.master_manager = MasterDataManager(temp_client)
        
        success, data = self.master_manager.load_equipment_master()
        
        if success and data:
            self._display_equipment_data(data)
            QMessageBox.information(
                self,
                "読み込み成功",
                f"設備分類マスタを読み込みました\n件数: {len(data)}"
            )
        else:
            QMessageBox.warning(
                self,
                "読み込み失敗",
                "設備分類マスタの読み込みに失敗しました\n"
                "キャッシュファイルが存在しないか、読み込みエラーが発生しました"
            )
    
    def _display_equipment_data(self, data: dict):
        """設備分類データをテーブルに表示"""
        # フルデータを保存（フィルタ用）
        self.equipment_full_data = data
        
        # テーブルをクリア
        self.equipment_table.setRowCount(0)
        
        # データを追加
        for code, name in sorted(data.items()):
            row = self.equipment_table.rowCount()
            self.equipment_table.insertRow(row)
            
            self.equipment_table.setItem(row, 0, QTableWidgetItem(code))
            self.equipment_table.setItem(row, 1, QTableWidgetItem(name))
        
        logger.info(f"設備分類テーブル表示: {len(data)} 件")
    
    def _on_equipment_filter_changed(self, text: str):
        """設備分類フィルタ変更時の処理"""
        filter_text = text.strip().lower()
        
        # フィルタが空の場合は全データを表示
        if not filter_text:
            self._display_equipment_data(self.equipment_full_data)
            return
        
        # フィルタリング実行
        filtered_data = {
            code: name 
            for code, name in self.equipment_full_data.items()
            if filter_text in name.lower()
        }
        
        # テーブルをクリア
        self.equipment_table.setRowCount(0)
        
        # フィルタ結果を表示
        for code, name in sorted(filtered_data.items()):
            row = self.equipment_table.rowCount()
            self.equipment_table.insertRow(row)
            
            self.equipment_table.setItem(row, 0, QTableWidgetItem(code))
            self.equipment_table.setItem(row, 1, QTableWidgetItem(name))
        
        logger.debug(f"設備分類フィルタ: {len(filtered_data)}/{len(self.equipment_full_data)} 件表示")


