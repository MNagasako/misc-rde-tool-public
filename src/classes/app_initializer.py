"""
アプリケーション初期化管理クラス
Browserクラスの初期化処理を分離し、責務を明確化する
"""
import os
import sys
import logging
from config.common import DEBUG_INFO_FILE, LOGIN_FILE, WEBVIEW_MESSAGE_LOG
from classes.managers.display_manager import DisplayManager
from classes.data_fetch.core.data_manager import DataManager
from classes.utils import HtmlLogger
from classes.managers.project_manager import ProjectManager
from classes.core import BatchProcessor
from classes.core import ImageProcessor
from classes.ui.controllers.ui_controller import UIController
from classes.utils.debug_log import debug_log


class AppInitializer:
    """アプリケーション初期化処理を管理するクラス"""
    
    def __init__(self, browser_instance):
        self.browser = browser_instance
        self.logger = logging.getLogger("RDE_WebView")
        
    @debug_log
    def initialize_managers(self):
        """各種マネージャークラスの初期化"""
        # DisplayManager初期化
        self.browser.display_manager = DisplayManager(
            webview_msg_label=self.browser.webview_msg_label,
            log_path=WEBVIEW_MESSAGE_LOG,
            max_len=110,
            autologin_msg_label=self.browser.autologin_msg_label
        )
        
        # DataManager初期化
        self.browser.data_manager = DataManager(self.logger)
        
        # HTMLLogger初期化
        self.browser.html_logger = HtmlLogger()
        
        # DataTreeManager初期化
        from classes.data_fetch.core.datatree_manager import DataTreeManager
        from config.common import DATATREE_FILE_PATH
        self.browser.datatree_manager = DataTreeManager(DATATREE_FILE_PATH, self.logger)
        
        # ProjectManager初期化
        self.browser.project_manager = ProjectManager(
            self.browser, self.browser.data_manager, self.browser.datatree_manager
        )
        
        # BatchProcessor初期化
        self.browser.batch_processor = BatchProcessor(self.browser)
        
        # ImageProcessor初期化
        self.browser.image_processor = ImageProcessor(self.browser)
        
        # UIController初期化
        self.browser.ui_controller = UIController(self.browser)
        
        self.logger.info("全マネージャークラスの初期化完了")
        
    @debug_log
    def setup_batch_signals(self):
        """BatchProcessorのシグナル接続"""
        self.browser.batch_processor.batch_progress_updated.connect(
            self.browser._on_batch_progress_updated
        )
        self.browser.batch_processor.batch_completed.connect(
            self.browser._on_batch_completed
        )
        self.browser.batch_processor.batch_error.connect(
            self.browser._on_batch_error
        )
        
    @debug_log
    def initialize_arim_anonymizer(self):
        """ARIM匿名化機能の初期化"""
        try:
            # パス管理システムを使用してモジュール読み込み
            from classes.utils.arim_anonymizer import ARIMAnonymizer

            anonymizer_logger = logging.getLogger('RDE_WebView')
            if not anonymizer_logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('[%(levelname)s] %(asctime)s - %(name)s: %(message)s')
                handler.setFormatter(formatter)
                anonymizer_logger.addHandler(handler)
                anonymizer_logger.setLevel(logging.DEBUG)

            self.browser.anonymizer = ARIMAnonymizer(anonymizer_logger)
            self.browser.logger = anonymizer_logger
            anonymizer_logger.info("[ARIM] 匿名化機能初期化完了")
            #self.browser.set_webview_message("[匿名化機能初期化完了")
            
        except Exception as e:
            self.logger.warning(f"匿名化機能初期化失敗: {e}")
            self.browser.config_manager = None
            self.browser.anonymizer = None
            self.browser.logger = None
            
    @debug_log
    def setup_login_info(self):
        """ログイン情報とinfo.txtの設定"""
        # login.txtのパス情報をinfo.txtに出力（バイナリ時はユーザーディレクトリ配下）
        info_path = DEBUG_INFO_FILE
        login_path = LOGIN_FILE
        login_info = f"login.txt path : {os.path.abspath(login_path)}"

        try:
            os.makedirs(os.path.dirname(info_path), exist_ok=True)
            with open(info_path, 'w', encoding='utf-8') as infof:
                infof.write(f"{login_info}\n")
        except Exception as e:
            self.logger.warning(f"info.txt書き込み失敗: {e}")
            
    @debug_log
    def initialize_proxy_settings(self):
        """プロキシ設定の自動初期化"""
        try:
            from net.session_manager import ProxySessionManager
            
            self.logger.info("プロキシ設定を初期化中...")
            proxy_manager = ProxySessionManager()
            
            # システムプロキシ情報を取得
            proxy_info = proxy_manager.get_system_proxy_info()
            
            if proxy_info.get("detected", False):
                self.logger.info(f"システムプロキシを検出: {proxy_info['proxies']}")
                
                # システムプロキシを自動設定として保存
                success = proxy_manager.create_system_proxy_config("system_auto")
                
                if success:
                    self.logger.info("システムプロキシ設定をsystem_autoとして保存しました")
                    
                    # SYSTEMモードを適用（WebViewとセッション管理の両方で自動プロキシ使用）
                    from config.common import get_dynamic_file_path
                    import yaml
                    
                    yaml_path = get_dynamic_file_path("config/network.yaml")
                    if os.path.exists(yaml_path):
                        with open(yaml_path, 'r', encoding='utf-8') as f:
                            config_data = yaml.safe_load(f) or {}
                        
                        # SYSTEMモードに設定（WebViewとrequests両方で自動プロキシ使用）
                        config_data["mode"] = "SYSTEM"
                        
                        with open(yaml_path, 'w', encoding='utf-8') as f:
                            yaml.safe_dump(config_data, f, default_flow_style=False, 
                                         allow_unicode=True, sort_keys=False)
                        
                        self.logger.info("プロキシモードをSYSTEMに設定しました")
                        self.browser.set_webview_message("[プロキシ設定完了] システムプロキシを自動適用")
                    
                    # プロキシ設定を適用
                    proxy_manager.configure()
                    session = proxy_manager.get_session()
                    
                    self.logger.info(f"プロキシセッション準備完了: {session.proxies}")
                else:
                    self.logger.warning("システムプロキシ設定の保存に失敗しました")
            else:
                self.logger.info("システムプロキシが検出されませんでした。DIRECT モードを使用します")
                self.browser.set_webview_message("[プロキシ設定] ダイレクト接続を使用")
                
                # プロキシなしの設定を適用
                proxy_manager.configure()
            
        except Exception as e:
            self.logger.warning(f"プロキシ設定初期化エラー: {e}")
            self.browser.set_webview_message("[プロキシ設定] 初期化エラー - デフォルト設定使用")
            
    @debug_log
    def initialize_all(self):
        """全初期化処理を実行"""        
        self.initialize_managers()
        
        # DisplayManager初期化後にプロキシ設定を初期化
        self.initialize_proxy_settings()
        
        self.setup_batch_signals()
        self.initialize_arim_anonymizer()
        self.setup_login_info()
        self.logger.info("アプリケーション初期化処理完了")
