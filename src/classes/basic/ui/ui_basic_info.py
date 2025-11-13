"""
basic_info関連のUIロジック分離
"""
import logging
from qt_compat.core import QTimer, Qt
from qt_compat.widgets import QProgressDialog, QMessageBox
import threading
from classes.utils.progress_worker import ProgressWorker, SimpleProgressWorker

# ロガー設定
logger = logging.getLogger(__name__)

def show_progress_dialog(parent, title, worker):
    """プログレス表示付きで処理を実行する共通関数"""
    progress_dialog = QProgressDialog(parent)
    progress_dialog.setWindowTitle(title)
    progress_dialog.setLabelText("処理を開始しています...")
    progress_dialog.setRange(0, 100)
    progress_dialog.setValue(0)
    progress_dialog.setWindowModality(Qt.WindowModal)
    progress_dialog.setCancelButtonText("キャンセル")
    progress_dialog.show()
    
    # プログレス更新の接続
    def update_progress(value, message):
        def set_progress():
            if progress_dialog:
                progress_dialog.setValue(value)
                progress_dialog.setLabelText(message)
        QTimer.singleShot(0, set_progress)
    
    # 完了時の処理
    def on_finished(success, message):
        def handle_finished():
            if progress_dialog:
                progress_dialog.close()
            if success:
                QMessageBox.information(parent, title, message)
            else:
                QMessageBox.critical(parent, f"{title} - エラー", message)
        QTimer.singleShot(0, handle_finished)
    
    # キャンセル処理
    def on_cancel():
        worker.cancel()
        progress_dialog.close()
    
    worker.progress.connect(update_progress)
    worker.finished.connect(on_finished)
    progress_dialog.canceled.connect(on_cancel)
    
    # ワーカーをスレッドで実行
    thread = threading.Thread(target=worker.run)
    thread.start()
    
    return progress_dialog

def fetch_basic_info(controller):
    """
    基本情報取得（全データセット）
    
    v2.0.1改善:
    - トークン検証の追加
    - エラーメッセージの明確化
    - 再ログイン促進機能の統合
    """
    try:
        from ..core.basic_info_logic import fetch_basic_info_logic, show_fetch_confirmation_dialog
        from core.bearer_token_manager import BearerTokenManager
        
        # トークン取得（v2.0.1: BearerTokenManagerを使用）
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
        
        # トークンが取得できない場合は処理を中止
        if not bearer_token:
            logger.warning("基本情報取得処理: トークンが取得できませんでした")
            QMessageBox.warning(
                controller.parent,
                "認証エラー",
                "認証トークンが取得できません。\n"
                "ログインタブでRDEシステムにログインしてから再度実行してください。"
            )
            return
        
        webview = getattr(controller.parent, 'webview', controller.parent)
        
        # 確認ダイアログをメインスレッドで表示
        if not show_fetch_confirmation_dialog(controller.parent, onlySelf=False, searchWords=None):
            logger.info("基本情報取得処理はユーザーによりキャンセルされました")
            return
        
        # プログレス表示付きワーカーを作成
        worker = ProgressWorker(
            task_func=fetch_basic_info_logic,
            task_kwargs={
                'bearer_token': bearer_token,
                'parent': controller.parent,
                'webview': webview,
                'onlySelf': False,
                'searchWords': None,
                'skip_confirmation': True
            },
            task_name="基本情報取得"
        )
        
        # プログレス表示
        show_progress_dialog(controller.parent, "基本情報取得", worker)
    except ImportError as e:
        logger.error(f"基本情報取得モジュールのインポートエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"基本情報取得機能の初期化に失敗しました: {e}")
    except Exception as e:
        logger.error(f"基本情報取得処理でエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"基本情報取得処理中にエラーが発生しました: {e}")

def fetch_basic_info_self(controller):
    """
    基本情報取得（検索条件付き）
    
    v2.0.1改善:
    - トークン検証の追加
    - エラーメッセージの明確化
    - 再ログイン促進機能の統合
    """
    try:
        from ..core.basic_info_logic import fetch_basic_info_logic, show_fetch_confirmation_dialog
        from core.bearer_token_manager import BearerTokenManager
        
        # トークン取得（v2.0.1: BearerTokenManagerを使用）
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
        
        # トークンが取得できない場合は処理を中止
        if not bearer_token:
            logger.warning("基本情報取得処理（検索）: トークンが取得できませんでした")
            QMessageBox.warning(
                controller.parent,
                "認証エラー",
                "認証トークンが取得できません。\n"
                "ログインタブでRDEシステムにログインしてから再度実行してください。"
            )
            return
        
        webview = getattr(controller.parent, 'webview', controller.parent)
        searchWords = controller.basic_info_input.text() if hasattr(controller, 'basic_info_input') else None
        
        # 確認ダイアログをメインスレッドで表示
        if not show_fetch_confirmation_dialog(controller.parent, onlySelf=True, searchWords=searchWords):
            logger.info("基本情報取得処理はユーザーによりキャンセルされました。")
            return
        
        # プログレス表示付きワーカーを作成
        worker = ProgressWorker(
            task_func=fetch_basic_info_logic,
            task_kwargs={
                'bearer_token': bearer_token,
                'parent': controller.parent,
                'webview': webview,
                'onlySelf': True,
                'searchWords': searchWords,
                'skip_confirmation': True
            },
            task_name="自分の基本情報取得"
        )
        
        # プログレス表示
        show_progress_dialog(controller.parent, "自分の基本情報取得", worker)
    except ImportError as e:
        logger.error(f"基本情報取得モジュールのインポートエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"基本情報取得機能の初期化に失敗しました: {e}")
    except Exception as e:
        logger.error(f"基本情報取得処理でエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"基本情報取得処理中にエラーが発生しました: {e}")

def summary_basic_info_to_Xlsx(controller):
    """
    基本情報をXLSXにまとめる
    
    v2.0.4改善:
    - BearerTokenManager統一
    - トークン検証の追加
    """
    try:
        from ..util.xlsx_exporter import summary_basic_info_to_Xlsx_logic
        from core.bearer_token_manager import BearerTokenManager
        
        # トークン取得
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
        
        # トークンが取得できない場合は処理を中止
        if not bearer_token:
            logger.warning("XLSX出力処理: トークンが取得できませんでした")
            QMessageBox.warning(
                controller.parent,
                "認証エラー",
                "認証トークンが取得できません。\n"
                "ログインタブでRDEシステムにログインしてから再度実行してください。"
            )
            return
        
        webview = getattr(controller.parent, 'webview', controller.parent)
        
        # プログレス表示付きワーカーを作成（詳細プログレス対応）
        worker = ProgressWorker(
            task_func=summary_basic_info_to_Xlsx_logic,
            task_kwargs={
                'bearer_token': bearer_token,
                'parent': controller.parent,
                'webview': webview
            },
            task_name="まとめXLSX作成"
        )
        
        # プログレス表示
        show_progress_dialog(controller.parent, "まとめXLSX作成", worker)
    except ImportError as e:
        logger.error(f"XLSX出力モジュールのインポートエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"XLSX出力機能の初期化に失敗しました: {e}")
    except Exception as e:
        logger.error(f"XLSX出力処理でエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"XLSX出力処理中にエラーが発生しました: {e}")

def apply_basic_info_to_Xlsx(controller):
    """
    基本情報をXLSXに反映
    
    v2.0.4改善:
    - BearerTokenManager統一
    - トークン検証の追加
    """
    try:
        from ..util.xlsx_exporter import apply_basic_info_to_Xlsx_logic
        from core.bearer_token_manager import BearerTokenManager
        
        # トークン取得
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
        
        # トークンが取得できない場合は処理を中止
        if not bearer_token:
            logger.warning("XLSX反映処理: トークンが取得できませんでした")
            QMessageBox.warning(
                controller.parent,
                "認証エラー",
                "認証トークンが取得できません。\n"
                "ログインタブでRDEシステムにログインしてから再度実行してください。"
            )
            return
        
        webview = getattr(controller.parent, 'webview', controller.parent)
        
        # プログレス表示付きワーカーを作成
        worker = SimpleProgressWorker(
            task_func=apply_basic_info_to_Xlsx_logic,
            task_kwargs={
                'bearer_token': bearer_token,
                'parent': controller.parent,
                'webview': webview
            },
            task_name="XLSX反映"
        )
        
        # プログレス表示
        show_progress_dialog(controller.parent, "XLSX反映", worker)
    except ImportError as e:
        logger.error(f"XLSX反映モジュールのインポートエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"XLSX反映機能の初期化に失敗しました: {e}")
    except Exception as e:
        logger.error(f"XLSX反映処理でエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"XLSX反映処理中にエラーが発生しました: {e}")

def fetch_invoice_schema(controller):
    """
    invoiceSchemasを取得する
    
    v2.0.4改善:
    - BearerTokenManager統一
    - トークン検証の追加
    """
    from ..core.basic_info_logic import fetch_invoice_schemas
    from core.bearer_token_manager import BearerTokenManager
    
    # トークン取得
    bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
    
    # トークンが取得できない場合は処理を中止
    if not bearer_token:
        logger.warning("invoiceSchemas取得処理: トークンが取得できませんでした")
        QMessageBox.warning(
            controller.parent,
            "認証エラー",
            "認証トークンが取得できません。\n"
            "ログインタブでRDEシステムにログインしてから再度実行してください。"
        )
        return
    
    output_dir = "output/rde/data"  # 必要に応じて動的に

    # プログレス表示付きワーカーを作成
    worker = ProgressWorker(
        task_func=fetch_invoice_schemas,
        task_kwargs={
            'bearer_token': bearer_token,
            'output_dir': output_dir
        },
        task_name="invoiceSchemas取得"
    )
    
    # プログレス表示
    show_progress_dialog(controller.parent, "invoiceSchemas取得", worker)

def fetch_sample_info_only(controller):
    """
    サンプル情報のみを強制取得する
    
    v2.0.4改善:
    - BearerTokenManager統一
    - トークン検証の追加
    """
    from ..core.basic_info_logic import fetch_sample_info_only as fetch_sample_info_only_logic
    from core.bearer_token_manager import BearerTokenManager
    
    # トークン取得
    bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
    
    # トークンが取得できない場合は処理を中止
    if not bearer_token:
        logger.warning("サンプル情報取得処理: トークンが取得できませんでした")
        QMessageBox.warning(
            controller.parent,
            "認証エラー",
            "認証トークンが取得できません。\n"
            "ログインタブでRDEシステムにログインしてから再度実行してください。"
        )
        return
    
    # 確認ダイアログ
    reply = QMessageBox.question(
        controller.parent, 
        "サンプル情報強制取得の確認",
        "全サンプル情報を強制取得しますか？\n\n実行内容:\n• 既存ファイルを上書き更新\n• subGroup.jsonの全グループIDでサンプル情報を取得\n• 最新のサンプル情報に更新\n\n※事前にサブグループ情報が必要です",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    
    if reply != QMessageBox.Yes:
        logger.info("サンプル情報強制取得処理はユーザーによりキャンセルされました。")
        return
    
    # プログレス表示付きワーカーを作成
    worker = ProgressWorker(
        task_func=fetch_sample_info_only_logic,
        task_kwargs={
            'bearer_token': bearer_token,
            'output_dir': "output/rde/data"
        },
        task_name="サンプル情報強制取得"
    )
    
    # プログレス表示
    show_progress_dialog(controller.parent, "サンプル情報強制取得", worker)

def fetch_common_info_only(controller):
    """
    9種類の共通情報JSONのみを取得する
    
    v2.0.1改善:
    - トークン検証の追加
    - エラーメッセージの明確化
    - 再ログイン促進機能の統合
    """
    from ..core.basic_info_logic import fetch_common_info_only_logic
    from core.bearer_token_manager import BearerTokenManager
    
    # トークン取得（v2.0.1: BearerTokenManagerを使用）
    bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
    
    # トークンが取得できない場合は処理を中止
    if not bearer_token:
        logger.warning("共通情報取得処理: トークンが取得できませんでした")
        QMessageBox.warning(
            controller.parent,
            "認証エラー",
            "認証トークンが取得できません。\n"
            "ログインタブでRDEシステムにログインしてから再度実行してください。"
        )
        return
    
    webview = getattr(controller.parent, 'webview', controller.parent)
    
    # 確認ダイアログ
    reply = QMessageBox.question(
        controller.parent, 
        "共通情報取得の確認",
        "9種類の共通情報JSONを更新しますか？\n\n取得対象:\n• ユーザー情報\n• グループ情報\n• 組織情報\n• 装置情報\n• テンプレート情報\n• データセット一覧\n\n※個別データセットJSONは取得しません",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    
    if reply != QMessageBox.Yes:
        logger.info("共通情報取得処理はユーザーによりキャンセルされました。")
        return
    
    # プログレス表示付きワーカーを作成
    worker = ProgressWorker(
        task_func=fetch_common_info_only_logic,
        task_kwargs={
            'bearer_token': bearer_token,
            'parent': controller.parent,
            'webview': webview
        },
        task_name="共通情報取得"
    )
    
    # プログレス表示
    def on_finished_with_refresh(success, message):
        def handle_finished():
            if success:
                QMessageBox.information(controller.parent, "共通情報取得", message)
                # JSON状況表示を更新
                QTimer.singleShot(100, lambda: refresh_json_status_display(controller))
            else:
                QMessageBox.critical(controller.parent, "共通情報取得 - エラー", message)
        QTimer.singleShot(0, handle_finished)
    
    # 通常のプログレス表示
    progress_dialog = show_progress_dialog(controller.parent, "共通情報取得", worker)
    
    # 完了時処理を上書き
    worker.finished.disconnect()  # 既存の接続を削除
    worker.finished.connect(on_finished_with_refresh)

def refresh_json_status_display(controller):
    """
    JSON取得状況表示を更新
    """
    if hasattr(controller, 'json_status_widget'):
        controller.json_status_widget.update_status()

def create_json_status_widget(parent=None):
    """
    JSON取得状況を表示するウィジェットを作成
    """
    from qt_compat.widgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
    from qt_compat.core import Qt
    
    class JsonStatusWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.init_ui()
            
        def init_ui(self):
            layout = QVBoxLayout(self)
            
            # タイトル
            #title_label = QLabel("JSON取得状況")
            #title_label.setStyleSheet("font-weight: bold; font-size: 12pt; color: #2E86AB;")
            #layout.addWidget(title_label)
            
            # 更新ボタン
            refresh_btn = QPushButton("状況更新")
            refresh_btn.setMaximumWidth(100)
            refresh_btn.clicked.connect(self.update_status)
            layout.addWidget(refresh_btn)
            
            # ステータス表示エリア
            self.status_text = QTextEdit()
            self.status_text.setReadOnly(True)
            self.status_text.setMaximumHeight(200)
            self.status_text.setStyleSheet("font-family: 'Consolas'; font-size: 9pt;")
            layout.addWidget(self.status_text)
            
            # 初期状態を表示
            self.update_status()
            
        def update_status(self):
            try:
                from ..core.basic_info_logic import get_json_status_info
                json_info = get_json_status_info()
                status_text = "【共通JSONファイル】\n"
                
                common_files = [
                    ("self.json", "ユーザー情報"),
                    ("group.json", "グループ情報"),
                    ("groupDetail.json", "グループ詳細"),
                    ("subGroup.json", "サブグループ"),
                    ("organization.json", "組織情報"),
                    ("instrumentType.json", "装置タイプ"),
                    ("template.json", "テンプレート"),
                    ("instruments.json", "設備情報"),
                    ("licenses.json", "利用ライセンス"),
                    ("info.json", "統合情報"),
                    ("dataset.json", "データセット一覧")
                ]
                
                for file_name, description in common_files:
                    info = json_info.get(file_name, {})
                    status = "✓" if info.get("exists") else "✗"
                    modified = info.get("modified", "未取得")
                    size = info.get("size_kb", 0)
                    status_text += f"{status} {description:12} | {modified} | {size:6.1f}KB\n"
                
                summary = json_info.get("summary", {})
                status_text += f"\n【個別JSONファイル】\n"
                status_text += f"個別データセット: {summary.get('individual_datasets', 0):4d} 件\n"
                status_text += f"データエントリ  : {summary.get('data_entries', 0):4d} 件\n"
                status_text += f"サンプル情報    : {summary.get('sample_files', 0):4d} 件\n"
                status_text += f"共通ファイル    : {summary.get('common_files_count', 0):4d}/11 件"
                
                self.status_text.setPlainText(status_text)
            except ImportError as e:
                self.status_text.setPlainText(f"モジュールインポートエラー: {e}")
            except Exception as e:
                self.status_text.setPlainText(f"状況取得エラー: {e}")
    
    return JsonStatusWidget(parent)

def execute_individual_stage_ui(controller, stage_name):
    """
    個別段階実行をUIから呼び出す
    """
    from ..core.basic_info_logic import execute_individual_stage, STAGE_FUNCTIONS
    
    if stage_name not in STAGE_FUNCTIONS:
        QMessageBox.warning(controller.parent, "エラー", f"不正な段階名です: {stage_name}")
        return
    
    # セパレータアイテムの場合は実行しない
    if STAGE_FUNCTIONS[stage_name] is None:
        QMessageBox.information(controller.parent, "情報", f"「{stage_name}」はセパレータです。実行できません。")
        return
    
    # トークン取得（v2.0.4）
    from core.bearer_token_manager import BearerTokenManager
    bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
    
    # トークンが取得できない場合は処理を中止
    if not bearer_token:
        logger.warning(f"個別段階実行（{stage_name}）: トークンが取得できませんでした")
        QMessageBox.warning(
            controller.parent,
            "認証エラー",
            "認証トークンが取得できません。\n"
            "ログインタブでRDEシステムにログインしてから再度実行してください。"
        )
        return
    
    webview = getattr(controller.parent, 'webview', controller.parent)
    
    # 確認ダイアログ
    reply = QMessageBox.question(
        controller.parent, 
        f"{stage_name}実行の確認",
        f"{stage_name}を個別実行しますか？\n\n実行対象: {stage_name}\n\n※前段階の情報が必要な場合があります",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    
    if reply != QMessageBox.Yes:
        logger.info(f"{stage_name}の個別実行はユーザーによりキャンセルされました")
        return
    
    # データセット情報の場合は検索条件を取得
    onlySelf = False
    searchWords = None
    if stage_name == "データセット情報" and hasattr(controller, 'basic_info_input'):
        search_text = controller.basic_info_input.text().strip()
        if search_text:
            onlySelf = True
            searchWords = search_text
    
    # プログレス表示付きワーカーを作成
    worker = ProgressWorker(
        task_func=execute_individual_stage,
        task_kwargs={
            'stage_name': stage_name,
            'bearer_token': bearer_token,
            'webview': webview,
            'onlySelf': onlySelf,
            'searchWords': searchWords
        },
        task_name=f"{stage_name}実行"
    )
    
    # プログレス表示
    def on_finished_with_refresh(success, message):
        def handle_finished():
            if success:
                QMessageBox.information(controller.parent, f"{stage_name}実行", message)
                # JSON状況表示を更新
                if hasattr(controller, 'json_status_widget'):
                    QTimer.singleShot(100, lambda: controller.json_status_widget.update_status())
            else:
                QMessageBox.critical(controller.parent, f"{stage_name}実行 - エラー", message)
        QTimer.singleShot(0, handle_finished)
    
    # 通常のプログレス表示
    progress_dialog = show_progress_dialog(controller.parent, f"{stage_name}実行", worker)
    
    # 完了時処理を上書き
    worker.finished.disconnect()  # 既存の接続を削除
    worker.finished.connect(on_finished_with_refresh)

def create_individual_execution_widget(parent=None):
    """
    個別実行用のドロップダウンとボタンを作成
    """
    from qt_compat.widgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                                QComboBox, QPushButton, QTextEdit)
    from qt_compat.core import QTimer
    from ..core.basic_info_logic import STAGE_FUNCTIONS
    
    class IndividualExecutionWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.controller = None  # 後で設定される
            self.init_ui()
            self.update_status_timer = QTimer()
            self.update_status_timer.timeout.connect(self.update_stage_status)
            self.update_status_timer.start(10000)  # 10秒ごとに更新
            
        def init_ui(self):
            layout = QVBoxLayout(self)
            
            # タイトル
            #title_label = QLabel("段階別個別実行")
            #title_label.setStyleSheet("font-weight: bold; font-size: 11pt; color: #2E86AB;")
            #layout.addWidget(title_label)
            
            # 実行コントロール行
            control_layout = QHBoxLayout()
            
            # ラベル
            label = QLabel("個別取得:")
            label.setMinimumWidth(70)
            control_layout.addWidget(label)
            
            # ドロップダウンリスト
            self.stage_combo = QComboBox()
            self.stage_combo.addItems(list(STAGE_FUNCTIONS.keys()))
            self.stage_combo.setMinimumWidth(200)
            self.stage_combo.currentTextChanged.connect(self.on_stage_selection_changed)
            control_layout.addWidget(self.stage_combo)
            
            # 実行ボタン
            self.execute_btn = QPushButton("実行")
            self.execute_btn.setMaximumWidth(80)
            self.execute_btn.clicked.connect(self.execute_stage)
            control_layout.addWidget(self.execute_btn)
            
            # 更新ボタン
            self.refresh_btn = QPushButton("状況更新")
            self.refresh_btn.setMaximumWidth(80)
            self.refresh_btn.clicked.connect(self.update_stage_status)
            control_layout.addWidget(self.refresh_btn)
            
            layout.addLayout(control_layout)
            
            # 段階完了状況表示エリア
            self.status_text = QTextEdit()
            self.status_text.setReadOnly(True)
            self.status_text.setMaximumHeight(150)
            self.status_text.setStyleSheet("font-family: 'Consolas'; font-size: 9pt;")
            layout.addWidget(self.status_text)
            
            # 初期状態を表示
            self.update_stage_status()
            
        def set_controller(self, controller):
            """コントローラーを設定"""
            self.controller = controller
            
        def execute_stage(self):
            """選択された段階を実行"""
            if not self.controller:
                QMessageBox.warning(self, "エラー", "コントローラーが設定されていません")
                return
                
            stage_name = self.stage_combo.currentText()
            execute_individual_stage_ui(self.controller, stage_name)
            
            # 実行後に状況を更新
            QTimer.singleShot(1000, self.update_stage_status)
            
        def on_stage_selection_changed(self):
            """段階選択が変更された時の処理"""
            self.update_stage_status()
            
        def update_stage_status(self):
            """段階完了状況を更新"""
            try:
                from ..core.basic_info_logic import get_stage_completion_status
                status_data = get_stage_completion_status()
                
                status_text = "【段階別完了状況】\n"
                selected_stage = self.stage_combo.currentText()
                
                for stage_name, stage_info in status_data.items():
                    completed = stage_info["completed"]
                    total = stage_info["total"]
                    rate = stage_info["rate"]
                    status = stage_info["status"]
                    
                    # 選択中の段階をハイライト
                    marker = "★" if stage_name == selected_stage else "　"
                    status_icon = "✓" if rate == 100 else "△" if rate > 0 else "✗"
                    
                    status_text += f"{marker}{status_icon} {stage_name:18} | {completed:2}/{total} | {rate:5.1f}% | {status}\n"
                
                # 全体の進捗情報
                total_stages = len(status_data)
                completed_stages = len([s for s in status_data.values() if s["rate"] == 100])
                partial_stages = len([s for s in status_data.values() if 0 < s["rate"] < 100])
                
                status_text += f"\n【全体進捗】完了: {completed_stages}/{total_stages}段階"
                if partial_stages > 0:
                    status_text += f", 部分完了: {partial_stages}段階"
                
                # 選択中段階の詳細
                if selected_stage in status_data:
                    selected_info = status_data[selected_stage]
                    status_text += f"\n\n【{selected_stage}】\n"
                    status_text += f"状況: {selected_info['status']}\n"
                    status_text += f"完了率: {selected_info['rate']:.1f}% ({selected_info['completed']}/{selected_info['total']})"
                
                # 自動更新機能の説明
                status_text += f"\n\n【自動更新機能】\n"
                status_text += f"✓ サブグループ作成成功→subGroup.json自動更新\n"
                status_text += f"✓ データセット開設成功→dataset.json自動更新"
                
                self.status_text.setPlainText(status_text)
                
            except ImportError as e:
                self.status_text.setPlainText(f"モジュールインポートエラー: {e}")
            except Exception as e:
                self.status_text.setPlainText(f"状況取得エラー: {e}")
                import traceback
                logger.error(f"段階状況更新エラー: {e}")
                logger.error(traceback.format_exc())
    
    return IndividualExecutionWidget(parent)
