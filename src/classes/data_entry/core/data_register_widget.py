"""
データ登録用UIウィジェット
"""
import os
import json
import logging
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, 
    QTextEdit, QLineEdit, QFileDialog, QFrame, QScrollArea, QMessageBox, QTabWidget
)
from qt_compat.core import Qt, Signal
from qt_compat.gui import QFont
from config.common import get_dynamic_file_path
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color
# ロガー設定
logger = logging.getLogger(__name__)


class DataRegisterWidget(QWidget):
    """データ登録用ウィジェット"""
    
    def __init__(self, parent=None, bearer_token=None):
        super().__init__(parent)
        self.bearer_token = bearer_token
        self.dataset_info = None
        self.selected_files = []
        self.selected_attachments = []
        
        self.init_ui()
        self.setup_filtered_dataset_dropdown()
        
        # データセット更新通知システムに登録
        self.setup_dataset_refresh_notification()
        
    def init_ui(self):
        """UIを初期化"""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # タイトル
        title_label = QLabel("データ登録")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # データセット選択セクション
        dataset_frame = QFrame()
        dataset_frame.setFrameStyle(QFrame.Box)
        dataset_layout = QVBoxLayout()
        
        dataset_label = QLabel("データセット選択:")
        dataset_label.setFont(QFont("", 10, QFont.Bold))
        dataset_layout.addWidget(dataset_label)
        
        # フィルタ付きドロップダウンのためのプレースホルダー
        self.dataset_dropdown_container = QWidget()
        dataset_layout.addWidget(self.dataset_dropdown_container)
        
        # データセット概要表示エリア
        self.dataset_summary_label = QLabel("データセット概要:")
        self.dataset_summary_label.setFont(QFont("", 9, QFont.Bold))
        dataset_layout.addWidget(self.dataset_summary_label)
        
        self.dataset_summary_text = QTextEdit()
        self.dataset_summary_text.setMaximumHeight(100)
        self.dataset_summary_text.setReadOnly(True)
        self.dataset_summary_text.setStyleSheet(
            f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};"
        )
        dataset_layout.addWidget(self.dataset_summary_text)
        
        dataset_frame.setLayout(dataset_layout)
        layout.addWidget(dataset_frame)
        
        # ファイル選択セクション
        file_frame = QFrame()
        file_frame.setFrameStyle(QFrame.Box)
        file_layout = QVBoxLayout()
        
        file_label = QLabel("アップロードファイル選択:")
        file_label.setFont(QFont("", 10, QFont.Bold))
        file_layout.addWidget(file_label)
        
        file_button_layout = QHBoxLayout()
        self.select_files_btn = QPushButton("ファイル選択")
        self.select_files_btn.clicked.connect(self.select_files)
        file_button_layout.addWidget(self.select_files_btn)
        
        self.select_attachments_btn = QPushButton("添付ファイル選択")
        self.select_attachments_btn.clicked.connect(self.select_attachments)
        file_button_layout.addWidget(self.select_attachments_btn)
        
        file_layout.addLayout(file_button_layout)
        
        # 選択されたファイル表示
        self.files_info_text = QTextEdit()
        self.files_info_text.setMaximumHeight(80)
        self.files_info_text.setReadOnly(True)
        self.files_info_text.setPlaceholderText("選択されたファイルがここに表示されます")
        file_layout.addWidget(self.files_info_text)
        
        file_frame.setLayout(file_layout)
        layout.addWidget(file_frame)
        
        # フォーム入力セクション
        form_frame = QFrame()
        form_frame.setFrameStyle(QFrame.Box)
        form_layout = QVBoxLayout()
        
        form_label = QLabel("データ情報入力:")
        form_label.setFont(QFont("", 10, QFont.Bold))
        form_layout.addWidget(form_label)
        
        # データ名入力
        self.data_name_input = QLineEdit()
        self.data_name_input.setPlaceholderText("データ名を入力")
        form_layout.addWidget(QLabel("データ名:"))
        form_layout.addWidget(self.data_name_input)
        
        # 説明入力
        self.description_input = QTextEdit()
        self.description_input.setMaximumHeight(60)
        self.description_input.setPlaceholderText("データの説明を入力")
        form_layout.addWidget(QLabel("説明:"))
        form_layout.addWidget(self.description_input)
        
        form_frame.setLayout(form_layout)
        layout.addWidget(form_frame)
        
        # データ登録ボタン
        self.register_btn = QPushButton("データ登録実行")
        self.register_btn.setMinimumHeight(40)
        self.register_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.register_btn.clicked.connect(self.execute_data_register)
        self.register_btn.setEnabled(False)  # 初期状態では無効化
        layout.addWidget(self.register_btn)
        
        # ここからタブ構成に切り替え: データ登録タブ + 登録状況タブ
        try:
            from classes.data_entry.ui.registration_status_widget import RegistrationStatusWidget
        except Exception:
            # フォールバック: 直接PySide6実体に依存するモジュールを再インポート
            import importlib
            mod = importlib.import_module('classes.data_entry.ui.registration_status_widget')
            RegistrationStatusWidget = getattr(mod, 'RegistrationStatusWidget')
        register_page = QWidget()
        register_page.setLayout(layout)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(register_page, "データ登録")
        self.status_widget = RegistrationStatusWidget(self)
        self.tabs.addTab(self.status_widget, "登録状況")
        root_layout = QVBoxLayout()
        root_layout.addWidget(self.tabs)
        self.setLayout(root_layout)
        
    def setup_filtered_dataset_dropdown(self):
        """チェックボックス形式フィルタ付きデータセットドロップダウンをセットアップ"""
        try:
            from classes.data_entry.util.data_entry_filter_checkbox import create_checkbox_filter_dropdown
            
            # 既存のcontainerをクリア
            layout = self.dataset_dropdown_container.layout()
            if layout:
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
            else:
                layout = QVBoxLayout(self.dataset_dropdown_container)
                layout.setContentsMargins(0, 0, 0, 0)
            
            # 新しいチェックボックスフィルタ付きドロップダウンを作成
            self.dataset_filter_widget = create_checkbox_filter_dropdown(self.dataset_dropdown_container)
            layout.addWidget(self.dataset_filter_widget)
            
            # ドロップダウンの参照を設定
            self.dataset_dropdown = self.dataset_filter_widget.dataset_dropdown
            
            # イベント接続
            self.dataset_dropdown.currentIndexChanged.connect(self.on_dataset_changed)
            
            logger.info("チェックボックス形式フィルタ付きドロップダウンを設定しました")
            
        except ImportError as e:
            logger.error("チェックボックスフィルタのインポートに失敗: %s", e)
            self.setup_fallback_dropdown()
        except Exception as e:
            logger.error("チェックボックスフィルタのセットアップに失敗: %s", e)
            self.setup_fallback_dropdown()
        except Exception as e:
            logger.error("フィルタ付きドロップダウンの設定に失敗: %s", e)
            self.setup_fallback_dropdown()
    
    def setup_fallback_dropdown(self):
        """フォールバック用の通常ドロップダウンをセットアップ"""
        layout = self.dataset_dropdown_container.layout()
        if not layout:
            layout = QVBoxLayout(self.dataset_dropdown_container)
            layout.setContentsMargins(0, 0, 0, 0)
        
        self.dataset_dropdown = QComboBox()
        self.dataset_dropdown.setMaxVisibleItems(10)
        layout.addWidget(self.dataset_dropdown)
        
        # イベント接続
        self.dataset_dropdown.currentIndexChanged.connect(self.on_dataset_changed)
        
        # 従来の読み込み方法を使用
        self.load_datasets()
        
    def load_datasets(self):
        """データセット一覧を読み込み"""
        try:
            dataset_json_path = get_dynamic_file_path("output/rde/data/dataset.json")
            if not os.path.exists(dataset_json_path):
                self.dataset_dropdown.addItem("データセット情報がありません")
                return
                
            with open(dataset_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            datasets = data.get("data", [])
            if not datasets:
                self.dataset_dropdown.addItem("データセットが見つかりません")
                return
                
            self.dataset_dropdown.addItem("データセットを選択してください")
            for dataset in datasets:
                dataset_id = dataset.get("id", "")
                dataset_name = dataset.get("attributes", {}).get("name", "名前不明")
                self.dataset_dropdown.addItem(f"{dataset_name} ({dataset_id[:8]}...)", dataset)
                
        except Exception as e:
            logger.error("データセット読み込み失敗: %s", e)
            self.dataset_dropdown.addItem("データセット読み込みエラー")
            
    def on_dataset_changed(self):
        """データセット選択変更時の処理"""
        current_index = self.dataset_dropdown.currentIndex()
        if current_index <= 0:  # "選択してください" が選ばれている場合
            self.dataset_info = None
            self.dataset_summary_text.clear()
            self.update_register_button_state()
            return
            
        # 選択されたデータセット情報を取得
        self.dataset_info = self.dataset_dropdown.itemData(current_index)
        if not self.dataset_info:
            self.dataset_summary_text.clear()
            self.update_register_button_state()
            return
            
        # データセット概要を表示
        self.show_dataset_summary()
        self.update_register_button_state()
        
    def show_dataset_summary(self):
        """データセット概要を表示"""
        if not self.dataset_info:
            return
            
        try:
            attributes = self.dataset_info.get("attributes", {})
            name = attributes.get("name", "名前不明")
            description = attributes.get("description", "説明なし")
            dataset_id = self.dataset_info.get("id", "ID不明")
            
            # 概要テキストを作成
            summary_text = f"データセット名: {name}\n"
            summary_text += f"ID: {dataset_id}\n"
            summary_text += f"説明: {description}"
            
            self.dataset_summary_text.setPlainText(summary_text)
            
        except Exception as e:
            logger.error("データセット概要表示失敗: %s", e)
            self.dataset_summary_text.setPlainText("概要の取得に失敗しました")
            
    def select_files(self):
        """ファイル選択ダイアログ"""
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "アップロードするファイルを選択", 
            "", 
            "Excel ファイル (*.xlsx);;すべてのファイル (*)"
        )
        if files:
            # Excelファイルのバリデーション
            valid_files = []
            invalid_files = []
            
            for file_path in files:
                if file_path.lower().endswith('.xlsx'):
                    valid_files.append(file_path)
                else:
                    invalid_files.append(os.path.basename(file_path))
            
            if invalid_files:
                QMessageBox.warning(
                    self, 
                    "ファイル形式エラー", 
                    f"以下のファイルはExcel形式(.xlsx)ではないため除外されました:\n" + 
                    "\n".join(invalid_files)
                )
            
            self.selected_files = valid_files
            self.update_files_info()
            self.update_register_button_state()
            
    def select_attachments(self):
        """添付ファイル選択ダイアログ"""
        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "添付ファイルを選択", 
            "", 
            "すべてのファイル (*)"
        )
        if files:
            self.selected_attachments = files
            self.update_files_info()
            
    def update_files_info(self):
        """選択されたファイル情報を更新"""
        info_text = ""
        
        if self.selected_files:
            info_text += f"アップロードファイル ({len(self.selected_files)}件):\n"
            for file_path in self.selected_files:
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                info_text += f"  - {filename} ({file_size:.2f} MB)\n"
                
        if self.selected_attachments:
            info_text += f"\n添付ファイル ({len(self.selected_attachments)}件):\n"
            for file_path in self.selected_attachments:
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                info_text += f"  - {filename} ({file_size:.2f} MB)\n"
                
        self.files_info_text.setPlainText(info_text.strip())
        
    def update_register_button_state(self):
        """データ登録ボタンの有効/無効状態を更新"""
        # 添付ファイル（self.selected_attachments）は一切判定に使わない
        # Excelファイルが選択されており、データセットが選択されている場合のみ有効化
        has_excel_files = len(self.selected_files) > 0 and all(
            file_path.lower().endswith('.xlsx') for file_path in self.selected_files
        )
        has_dataset = self.dataset_info is not None

        # 添付ファイルの有無は一切関係しない
        self.register_btn.setEnabled(has_excel_files and has_dataset)

        # ボタンのツールチップでステータスを表示
        if not has_dataset:
            self.register_btn.setToolTip("データセットを選択してください")
        elif not has_excel_files:
            if len(self.selected_files) == 0:
                self.register_btn.setToolTip("Excelファイル(.xlsx)を選択してください")
            else:
                self.register_btn.setToolTip("有効なExcelファイル(.xlsx)を選択してください")
        else:
            self.register_btn.setToolTip("データ登録を実行します")
        
    def execute_data_register(self):
        """データ登録実行"""
        if not self.bearer_token:
            QMessageBox.warning(self, "認証エラー", "ログインが必要です")
            return
            
        if not self.dataset_info:
            QMessageBox.warning(self, "選択エラー", "データセットを選択してください")
            return
            
        if not self.selected_files:
            QMessageBox.warning(self, "ファイルエラー", "アップロードファイルを選択してください")
            return
            
        # フォーム値を収集
        form_values = {
            'dataName': self.data_name_input.text() or "データ名",
            'basicDescription': self.description_input.toPlainText() or "説明",
        }
        
        # 試料フォームのデータを取得
        sample_data = self.get_sample_form_data()
        if sample_data:
            form_values.update(sample_data)
        
        try:
            # データ登録ロジックを実行
            from .data_register_logic import run_data_register_logic
            run_data_register_logic(
                parent=self,
                bearer_token=self.bearer_token,
                dataset_info=self.dataset_info,
                form_values=form_values,
                file_paths=self.selected_files,
                attachment_paths=self.selected_attachments
            )
        except Exception as e:
            QMessageBox.critical(self, "実行エラー", f"データ登録の実行に失敗しました:\n{e}")

    def get_sample_form_data(self):
        """試料フォームのデータを取得"""
        if not hasattr(self, 'sample_input_widgets'):
            logger.debug("試料フォームの参照がありません")
            return None
            
        try:
            # 既存試料が選択されているかチェック
            selected_sample_data = None
            if hasattr(self, 'sample_combo'):
                current_index = self.sample_combo.currentIndex()
                if current_index > 0:  # "新規作成"以外が選択された場合
                    selected_sample_data = self.sample_combo.currentData()
            
            if selected_sample_data:
                # 既存試料選択の場合：試料IDを使用
                sample_id = selected_sample_data.get('id')
                logger.debug("既存試料選択: sample_id=%s", sample_id)
                
                if not sample_id:
                    QMessageBox.warning(self, "選択エラー", "選択された試料のIDが取得できませんでした。")
                    return None
                
                return {
                    'sampleId': sample_id,
                    'sampleNames': selected_sample_data.get('name', ''),  # 参考値として保持
                    'sampleDescription': selected_sample_data.get('description', ''),
                    'sampleComposition': selected_sample_data.get('composition', '')
                }
            else:
                # 新規試料作成の場合：フォームの入力値を使用
                sample_name = self.sample_input_widgets["name"].text().strip()
                sample_description = self.sample_input_widgets["description"].toPlainText().strip()
                sample_composition = self.sample_input_widgets["composition"].text().strip()
                
                logger.debug("新規試料作成: name='%s', desc='%s', comp='%s'", sample_name, sample_description, sample_composition)
                
                # 試料名のバリデーション
                if not sample_name:
                    QMessageBox.warning(self, "入力エラー", "試料名が入力されていません。")
                    return None
                
                return {
                    'sampleNames': sample_name,
                    'sampleDescription': sample_description,
                    'sampleComposition': sample_composition
                }
        except Exception as e:
            logger.error("試料フォームデータ取得エラー: %s", e)
            QMessageBox.critical(self, "フォームエラー", f"試料フォームのデータを取得できませんでした:\n{e}")
            return None
    
    def setup_dataset_refresh_notification(self):
        """データセット更新通知システムに登録"""
        try:
            from classes.dataset.util.dataset_refresh_notifier import get_dataset_refresh_notifier
            dataset_notifier = get_dataset_refresh_notifier()
            dataset_notifier.register_callback(self.refresh_dataset_list)
            logger.info("データ登録ウィジェット: データセット更新通知に登録完了")
            
            # ウィジェット破棄時の通知解除用
            def cleanup_callback():
                dataset_notifier.unregister_callback(self.refresh_dataset_list)
                logger.info("データ登録ウィジェット: データセット更新通知を解除")
            
            self._cleanup_dataset_callback = cleanup_callback
            
        except Exception as e:
            logger.warning("データセット更新通知への登録に失敗: %s", e)
    
    def refresh_dataset_list(self):
        """データセットリストを更新"""
        try:
            # ウィジェットが破棄されていないかチェック
            if not self.dataset_dropdown or self.dataset_dropdown.parent() is None:
                logger.debug("データセットコンボボックスが破棄されているため更新をスキップ")
                return
            
            logger.info("データセットリスト更新開始")
            
            # 現在選択されているアイテムのIDを保存
            current_dataset_id = None
            current_index = self.dataset_dropdown.currentIndex()
            if current_index > 0:  # 0番目は通常「選択してください」
                current_data = self.dataset_dropdown.itemData(current_index)
                if current_data:
                    current_dataset_id = current_data.get("id")
            
            # データセットリストを再読み込み
            self.load_datasets()
            
            # 以前の選択を復元
            if current_dataset_id:
                for i in range(self.dataset_dropdown.count()):
                    item_data = self.dataset_dropdown.itemData(i)
                    if item_data and item_data.get("id") == current_dataset_id:
                        self.dataset_dropdown.setCurrentIndex(i)
                        logger.info("データセット選択を復元: %s", current_dataset_id)
                        break
            
            logger.info("データセットリスト更新完了")
            
        except Exception as e:
            logger.error("データセットリスト更新に失敗: %s", e)
    
    def closeEvent(self, event):
        """ウィジェット終了時の処理"""
        try:
            if hasattr(self, '_cleanup_dataset_callback'):
                self._cleanup_dataset_callback()
        except Exception as e:
            logger.warning("データセット更新通知の解除に失敗: %s", e)
        super().closeEvent(event)
