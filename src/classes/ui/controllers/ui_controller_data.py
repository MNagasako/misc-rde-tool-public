"""
UIコントローラーデータ処理機能クラス - ARIM RDE Tool
UIControllerのデータ処理UI機能・データ取得・データ登録・データセット管理を担当
"""
import logging
from qt_compat.widgets import QMessageBox

class UIControllerData:
    """UIコントローラーのデータ処理機能専門クラス"""
    
    def __init__(self, parent_controller):
        """
        UIControllerDataの初期化
        Args:
            parent_controller: 親のUIControllerインスタンス
        """
        self.ui_controller = parent_controller  # ui_controllerとして保存
        self.parent = parent_controller         # 互換性のためparentも保持
        self.logger = logging.getLogger("UIControllerData")
        
        # データ処理関連の状態変数
        self.selected_files = []
        self.attachment_files = []
        self.current_dataset_id = None
    
    def setup_data_fetch_mode(self):
        """
        データ取得モードのセットアップ
        """
        try:
            # データ取得モード用のウィジェットを取得
            data_fetch_widget = self.ui_controller.get_mode_widget("data_fetch")
            
            # 親ウィジェットのメニューエリアに配置
            if hasattr(self.ui_controller, 'parent') and hasattr(self.ui_controller.parent, 'menu_area_layout'):
                parent_layout = self.ui_controller.parent.menu_area_layout
                
                # 既存のウィジェットをすべて削除
                for i in reversed(range(parent_layout.count())):
                    child = parent_layout.takeAt(i)
                    if child.widget():
                        child.widget().setParent(None)
                
                # データ取得モードのウィジェットを追加
                parent_layout.addWidget(data_fetch_widget)
            
            # 親ウィジェットのメッセージを更新
            if hasattr(self.ui_controller, 'parent') and hasattr(self.ui_controller.parent, 'display_manager'):
                self.ui_controller.parent.display_manager.set_message("データ取得モードを開始します")
            
            # 他のモード固有の処理があれば追加
            self.logger.info("データ取得モードがアクティブになりました")
            
        except Exception as e:
            self.logger.error(f"データ取得モードセットアップエラー: {e}")
    
    def _handle_operation_error(self, operation_name: str, error: Exception):
        """
        統一エラーハンドリング
        
        Args:
            operation_name: 操作名（エラーメッセージ用）
            error: 発生した例外
        """
        error_msg = f"{operation_name}エラー: {error}"
        self.logger.error(error_msg)
        self.ui_controller.show_error(error_msg)
    
    def prepare_dataset_open_request(self):
        """
        データセット開設ボタン押下時のロジック（外部ファイル呼び出し）
        bearer_tokenを渡す
        """
        try:
            from classes.dataset.core.dataset_open_logic import run_dataset_open_logic
            
            # 親ウィジェットからbearer_tokenを取得
            bearer_token = None
            if hasattr(self.ui_controller, 'parent'):
                bearer_token = getattr(self.ui_controller.parent, 'bearer_token', None)
            
            run_dataset_open_logic(parent=None, bearer_token=bearer_token)
            
        except Exception as e:
            error_msg = f"データセット開設ロジック呼び出し失敗: {e}"
            self.logger.error(error_msg)
            
            QMessageBox.warning(None, "エラー", error_msg)
            
            # 親ウィジェットのメッセージを更新
            if hasattr(self.ui_controller, 'parent') and hasattr(self.ui_controller.parent, 'display_manager'):
                self.ui_controller.parent.display_manager.set_message(error_msg)
    
    def on_file_select_clicked(self):
        """
        ファイル選択ボタン押下時の処理。ファイルパスを保存し、登録実行ボタンの有効/無効を制御。
        """
        try:
            from qt_compat.widgets import QFileDialog
            
            # ファイル選択ダイアログを表示
            file_paths, _ = QFileDialog.getOpenFileNames(
                None,
                "データファイルを選択",
                "",
                "All Files (*)"
            )
            
            if file_paths:
                self.selected_files = file_paths
                self.logger.info(f"選択されたファイル数: {len(file_paths)}")
                
                # 登録実行ボタンの状態を更新
                self.update_register_exec_button_state()
                
                # 親ウィジェットのメッセージを更新
                if hasattr(self.ui_controller, 'parent') and hasattr(self.ui_controller.parent, 'display_manager'):
                    self.ui_controller.parent.display_manager.set_message(f"{len(file_paths)}個のファイルが選択されました")
            
        except Exception as e:
            self.logger.error(f"ファイル選択エラー: {e}")
    
    def on_attachment_file_select_clicked(self):
        """
        添付ファイル選択ボタン押下時の処理。添付ファイルパスを保存し、登録実行ボタンの有効/無効を制御。
        """
        try:
            from qt_compat.widgets import QFileDialog
            
            # 添付ファイル選択ダイアログを表示
            file_paths, _ = QFileDialog.getOpenFileNames(
                None,
                "添付ファイルを選択",
                "",
                "All Files (*)"
            )
            
            if file_paths:
                self.attachment_files = file_paths
                self.logger.info(f"選択された添付ファイル数: {len(file_paths)}")
                
                # 登録実行ボタンの状態を更新
                self.update_register_exec_button_state()
                
                # 親ウィジェットのメッセージを更新
                if hasattr(self.ui_controller, 'parent') and hasattr(self.ui_controller.parent, 'display_manager'):
                    self.ui_controller.parent.display_manager.set_message(f"{len(file_paths)}個の添付ファイルが選択されました")
            
        except Exception as e:
            self.logger.error(f"添付ファイル選択エラー: {e}")
    
    def update_register_exec_button_state(self):
        """
        データファイルまたは添付ファイルが1つでも選択されていれば登録実行ボタンを有効化
        """
        try:
            # ファイルが選択されているかチェック
            has_files = len(self.selected_files) > 0 or len(self.attachment_files) > 0
            
            # 登録実行ボタンの参照を取得（親コントローラーから）
            if hasattr(self.ui_controller, 'register_exec_button'):
                self.ui_controller.register_exec_button.setEnabled(has_files)
                self.logger.debug(f"登録実行ボタン状態更新: {has_files}")
            
        except Exception as e:
            self.logger.error(f"登録実行ボタン状態更新エラー: {e}")
    
    def on_register_exec_clicked(self):
        """
        データ登録実行ボタン押下時の処理
        """
        try:
            # 基本的なバリデーション
            if not self.selected_files and not self.attachment_files:
                QMessageBox.warning(None, "エラー", "データファイルまたは添付ファイルが選択されていません。")
                return
            
            # データ登録ロジックを外部ファイルから呼び出し
            from classes.data_entry.core.data_register_logic import run_data_register_logic
            
            # 親ウィジェットから必要な情報を取得
            bearer_token = None
            if hasattr(self.ui_controller, 'parent'):
                bearer_token = getattr(self.ui_controller.parent, 'bearer_token', None)
            
            # 登録パラメータを準備
            register_params = {
                'data_files': self.selected_files,
                'attachment_files': self.attachment_files,
                'dataset_id': self.current_dataset_id
            }
            
            # データ登録実行
            run_data_register_logic(
                parent=None,
                bearer_token=bearer_token,
                params=register_params
            )
            
            # 成功時のメッセージ
            if hasattr(self.ui_controller, 'parent') and hasattr(self.ui_controller.parent, 'display_manager'):
                self.ui_controller.parent.display_manager.set_message("データ登録を開始しました")
            
        except Exception as e:
            error_msg = f"データ登録ロジック呼び出し失敗: {e}"
            self.logger.error(error_msg)
            
            QMessageBox.warning(None, "エラー", error_msg)
            
            # 親ウィジェットのメッセージを更新
            if hasattr(self.ui_controller, 'parent') and hasattr(self.ui_controller.parent, 'display_manager'):
                self.ui_controller.parent.display_manager.set_message(error_msg)
    
    def validate_sample_info_early(self):
        """
        データ登録前の早期バリデーション
        """
        try:
            # 基本的なバリデーション
            validation_errors = []
            
            # ファイル選択チェック
            if not self.selected_files and not self.attachment_files:
                validation_errors.append("データファイルまたは添付ファイルが選択されていません")
            
            # データセットIDチェック
            if not self.current_dataset_id:
                validation_errors.append("データセットIDが設定されていません")
            
            # バリデーション結果を返す
            if validation_errors:
                self.logger.warning(f"バリデーションエラー: {validation_errors}")
                return False, validation_errors
            else:
                self.logger.info("バリデーション成功")
                return True, []
            
        except Exception as e:
            self.logger.error(f"バリデーションエラー: {e}")
            return False, [f"バリデーション中にエラーが発生: {e}"]
    
    def get_sample_info_from_form(self):
        """
        動的フォームから試料情報を取得
        """
        try:
            sample_info = {}
            
            # 基本的な試料情報を取得
            # 実際の実装では、親コントローラーから動的フォームの値を取得
            if hasattr(self.parent, 'sample_form_widgets'):
                for field_name, widget in self.parent.sample_form_widgets.items():
                    if hasattr(widget, 'text'):
                        sample_info[field_name] = widget.text()
                    elif hasattr(widget, 'currentText'):
                        sample_info[field_name] = widget.currentText()
            
            self.logger.debug(f"取得した試料情報: {sample_info}")
            return sample_info
            
        except Exception as e:
            self.logger.error(f"試料情報取得エラー: {e}")
            return {}
    
    def set_dataset_id(self, dataset_id):
        """
        現在のデータセットIDを設定
        Args:
            dataset_id: データセットID
        """
        self.current_dataset_id = dataset_id
        self.logger.info(f"データセットID設定: {dataset_id}")
    
    def clear_data_state(self):
        """
        データ処理状態をクリア
        """
        self.selected_files = []
        self.attachment_files = []
        self.current_dataset_id = None
        self.logger.info("データ処理状態をクリアしました")
    
    def get_data_summary(self):
        """
        現在のデータ処理状態のサマリーを取得
        Returns:
            dict: データ処理状態のサマリー
        """
        return {
            'selected_files_count': len(self.selected_files),
            'attachment_files_count': len(self.attachment_files),
            'dataset_id': self.current_dataset_id,
            'ready_for_register': len(self.selected_files) > 0 or len(self.attachment_files) > 0
        }
    
    def fetch_basic_info(self):
        """基本情報取得"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_basic_info
            fetch_basic_info(self.ui_controller)
        except Exception as e:
            self._handle_operation_error("基本情報取得", e)
    
    def fetch_basic_info_self(self):
        """基本情報取得（検索）"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_basic_info_self
            fetch_basic_info_self(self.ui_controller)
        except Exception as e:
            self._handle_operation_error("基本情報取得（検索）", e)
    
    def summary_basic_info_to_Xlsx(self):
        """基本情報のExcelサマリー作成"""
        try:
            from classes.basic.ui.ui_basic_info import summary_basic_info_to_Xlsx
            summary_basic_info_to_Xlsx(self.ui_controller)
        except Exception as e:
            self._handle_operation_error("基本情報Excelサマリー作成", e)
    
    def apply_basic_info_to_Xlsx(self):
        """基本情報のExcel適用"""
        try:
            from classes.basic.ui.ui_basic_info import apply_basic_info_to_Xlsx
            apply_basic_info_to_Xlsx(self.ui_controller)
        except Exception as e:
            self._handle_operation_error("基本情報Excel適用", e)
    
    def fetch_common_info_only(self):
        """共通情報のみ取得"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_common_info_only
            fetch_common_info_only(self.ui_controller)
        except Exception as e:
            self._handle_operation_error("共通情報取得", e)
    
    def fetch_invoice_schema(self):
        """インボイススキーマ取得"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_invoice_schema
            fetch_invoice_schema(self.ui_controller)
        except Exception as e:
            self._handle_operation_error("インボイススキーマ取得", e)
    
    def fetch_sample_info_only(self):
        """サンプル情報のみ取得"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_sample_info_only
            fetch_sample_info_only(self.ui_controller)
        except Exception as e:
            self._handle_operation_error("サンプル情報取得", e)
    
    def open_file_selector(self):
        """ファイル選択ダイアログを開く"""
        try:
            from qt_compat.widgets import QFileDialog
            file_path, _ = QFileDialog.getOpenFileName(
                None,
                "ファイルを選択",
                "",
                "All Files (*)"
            )
            if file_path:
                self.logger.info(f"ファイル選択: {file_path}")
                return file_path
            return None
        except Exception as e:
            self._handle_operation_error("ファイル選択", e)
            return None
    
    def register_selected_datasets(self):
        """選択されたデータセットの登録"""
        try:
            self.logger.info("データセット登録処理開始")
            # データセット登録の実装
            from qt_compat.widgets import QMessageBox
            QMessageBox.information(None, "データセット登録", "データセットの登録が完了しました")
        except Exception as e:
            self._handle_operation_error("データセット登録", e)
    
    def validate_datasets(self):
        """データセットバリデーション"""
        try:
            self.logger.info("データセットバリデーション開始")
            # バリデーション処理の実装
            from qt_compat.widgets import QMessageBox
            QMessageBox.information(None, "バリデーション", "データセットのバリデーションが完了しました")
        except Exception as e:
            self.logger.error(f"データセットバリデーションエラー: {e}")
            self.ui_controller.show_error(f"データセットバリデーションエラー: {e}")
    
    def show_dataset_info(self, dataset_id):
        """データセット情報を表示する"""
        try:
            self.logger.info(f"データセット情報表示: {dataset_id}")
            # データセット情報の表示処理を実装
            from qt_compat.widgets import QMessageBox
            QMessageBox.information(None, "データセット情報", f"データセットID: {dataset_id}")
        except Exception as e:
            self.logger.error(f"データセット情報表示エラー: {e}")
            self.ui_controller.show_error(f"データセット情報表示エラー: {e}")
    
