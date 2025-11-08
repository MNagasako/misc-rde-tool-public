"""
EventHandlerManager - ARIM RDE Tool v1.13.1
メインアプリケーションのイベント処理統合管理クラス
UIイベント・フォーム処理・ボタンクリック処理の統合管理
Phase 6.1: 更なる責務分離による300行以下目標達成
"""

import logging

logger = logging.getLogger(__name__)

# debug_logの軽量版実装（config.common依存回避）
def debug_log(func):
    """デバッグログデコレータ（軽量版）"""
    import functools
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

class EventHandlerManager:
    """メインアプリケーションのイベント処理を統合管理するクラス"""
    
    def __init__(self, parent_app):
        self.parent = parent_app
        self.logger = logger
        
    @debug_log
    def on_url_changed(self, url):
        """URL変更時の処理（BrowserControllerに委譲）"""
        self.parent.browser_controller.on_url_changed(url)

    @debug_log
    def on_grant_number_decided(self, *args, **kwargs):
        """課題番号決定時の処理"""
        # grantNumber入力欄と決定ボタンを一時的に無効化（多重実行防止）
        self.parent.grant_input.setDisabled(True)
        self.parent.grant_btn.setDisabled(True)
        
        # 入力されたgrantNumberを取得
        new_grant_number = self.parent.grant_input.text().strip()
        
        # ProjectManagerに処理を委譲
        success = self.parent.project_manager.process_grant_number(new_grant_number)
        
        # 処理完了後、入力欄とボタンを再有効化
        self.parent.grant_input.setDisabled(False)
        self.parent.grant_btn.setDisabled(False)
        
        return success

    @debug_log
    def on_load_finished(self, ok):
        """ページ読み込み完了時の処理"""
        if hasattr(self.parent, 'browser_controller'):
            self.parent.browser_controller.on_load_finished(ok)

    @debug_log
    def closeEvent(self, event):
        """アプリケーション終了時の処理"""
        event.accept()

    @debug_log
    def execute_batch_grant_numbers(self, checked=False):
        """一括処理実行（BatchProcessorに委譲）"""
        if hasattr(self.parent, 'batch_processor'):
            return self.parent.batch_processor.execute_batch_grant_numbers()
        return False

    @debug_log
    def fetch_and_save_data_list(self, id, subdir, headers, datatree_json_path):
        """データリスト取得・保存（DataManagerに委譲）"""
        if hasattr(self.parent, 'data_manager'):
            return self.parent.data_manager.fetch_and_save_data_list(id, subdir, headers, datatree_json_path)
        return False

    @debug_log
    def process_dataset_id(self, id, name, details_dir, headers, fetch_and_save_data_list=None):
        """データセットID処理（DataManagerに委譲）"""
        if hasattr(self.parent, 'data_manager'):
            return self.parent.data_manager.process_dataset_id(
                id, name, details_dir, headers, fetch_and_save_data_list
            )
        return False

    @debug_log
    def fetch_and_save_dataset_detail(self, id, subdir, headers, datatree_json_path):
        """データセット詳細取得・保存（DataManagerに委譲）"""
        # コールバック関数を定義
        def fetch_and_save_data_list_callback(id, subdir, headers, datatree_json_path):
            return self.parent.data_manager.fetch_and_save_data_list(id, subdir, headers, datatree_json_path)
        
        def fetch_data_list_json_callback(headers, id):
            return self.parent.data_manager.fetch_data_list_json(headers, id)
        
        if hasattr(self.parent, 'data_manager'):
            return self.parent.data_manager.fetch_and_save_dataset_detail(
                id=id, 
                subdir=subdir, 
                headers=headers, 
                fetch_and_save_data_list=fetch_and_save_data_list_callback,
                fetch_data_list_json=fetch_data_list_json_callback,
                datatree_json_path=datatree_json_path
            )
        return False

    @debug_log
    def handle_blob_images(self, dir_path, result, data_id=None):
        """blob画像データ保存（ImageProcessorに委譲）"""
        if hasattr(self.parent, 'image_processor'):
            self.parent.image_processor.handle_blob_images(dir_path, result, data_id)

    @debug_log
    def switch_mode(self, mode):
        """モード切り替え（UIControllerに委譲）"""
        if hasattr(self.parent, 'ui_controller'):
            self.parent.ui_controller.switch_mode(mode)

    @debug_log
    def show_grant_number_form(self):
        """課題番号入力フォームの表示（UIControllerに委譲）"""
        if hasattr(self.parent, 'ui_controller'):
            self.parent.ui_controller.show_grant_number_form()
        
    @debug_log
    def update_image_limit(self, value):
        """画像制限更新（UIControllerに委譲）"""
        if hasattr(self.parent, 'ui_controller'):
            self.parent.ui_controller.update_image_limit(value)

    @debug_log
    def log_webview_html(self, url=None):
        """HTML ログ出力（HtmlLoggerに委譲）"""
        if hasattr(self.parent, 'html_logger'):
            self.parent.html_logger.log_webview_html(self.parent.webview, url)

    @debug_log
    def save_cookies_and_show_grant_form(self):
        """クッキー保存・フォーム表示処理"""
        self.parent.webview.page().profile().cookieStore().loadAllCookies()
        def save_cookies():
            if self.parent.cookies:
                from config.common import COOKIE_FILE_RDE
                with open(COOKIE_FILE_RDE, 'w', encoding='utf-8') as f:
                    for domain, name, value in self.parent.cookies:
                        f.write(f"{name}={value}; ")
                logger.info('Cookieを保存しました。grantNumberフォームを表示します。')
                self.parent.webview.setEnabled(False)
                self.parent.webview.setStyleSheet("background: transparent;")
                self.show_grant_number_form()
            else:
                logger.info('Cookieが取得できませんでした。')
        from qt_compat.core import QTimer
        QTimer.singleShot(1000, save_cookies)

    @debug_log
    def on_load_finished(self, ok):
        """ページロード完了時の処理（BrowserControllerに委譲）"""
        if hasattr(self.parent, 'browser_controller'):
            self.parent.browser_controller.on_load_finished(ok)

    @debug_log
    def _start_blob_image_polling(self, data_id, subdir, headers):
        """blob画像ポーリング開始（ImageProcessorに委譲）"""
        if hasattr(self.parent, 'image_processor'):
            self.parent.image_processor._start_blob_image_polling(data_id, subdir, headers)

    @debug_log
    def _extract_and_save_blob_images(self, blob_srcs, loop, max_images=None, data_id=None):
        """blob画像抽出・保存（ImageProcessorに委譲）"""
        if hasattr(self.parent, 'image_processor'):
            self.parent.image_processor._extract_and_save_blob_images(blob_srcs, loop, max_images, data_id)

    @debug_log
    def _hash_blob(self, b64, filename):
        """blob画像ハッシュ計算（ImageProcessorに委譲）"""
        if hasattr(self.parent, 'image_processor'):
            return self.parent.image_processor._hash_blob(b64, filename)
        return None

    @debug_log
    def center_window(self):
        """ウィンドウを画面中央に移動（UIControllerに委譲）"""
        if hasattr(self.parent, 'ui_controller'):
            self.parent.ui_controller.center_window()

    @debug_log
    def _on_batch_progress_updated(self, current, total):
        """バッチ処理進行状況の更新"""
        progress_message = f"バッチ処理進行中: {current}/{total}"
        if hasattr(self.parent, 'set_webview_message'):
            self.parent.set_webview_message(progress_message)
        logger.info(progress_message)

    @debug_log
    def _on_batch_completed(self, results):
        """バッチ処理完了時の処理"""
        total = results.get('total', 0)
        success = results.get('success', 0)
        errors = results.get('errors', 0)
        
        completion_message = f"バッチ処理完了: 成功={success}, エラー={errors}, 合計={total}"
        if hasattr(self.parent, 'set_webview_message'):
            self.parent.set_webview_message(completion_message)
        logger.info(completion_message)
        
        # 結果詳細をログに出力
        if 'results' in results:
            for grant_num, result in results['results'].items():
                status = result.get('status', 'unknown')
                if status == 'error':
                    logger.warning(f"  {grant_num}: エラー - {result.get('error', '不明')}")
                else:
                    logger.info(f"  {grant_num}: {status}")

    @debug_log
    def _on_batch_error(self, error_message):
        """バッチ処理エラー時の処理"""
        error_msg = f"バッチ処理エラー: {error_message}"
        if hasattr(self.parent, 'set_webview_message'):
            self.parent.set_webview_message(error_msg)
        logger.error(error_msg)

    @debug_log
    def apply_arim_anonymization(self, dataset_dir, grant_number):
        """ARIM匿名化処理（DataManagerに委譲）"""
        if hasattr(self.parent, 'data_manager'):
            self.parent.data_manager.apply_arim_anonymization(
                dataset_dir, grant_number, 
                set_webview_message=getattr(self.parent, 'set_webview_message', None)
            )

    @debug_log
    def process_dataset_id(self, id, name, details_dir, headers, fetch_and_save_data_list=None):
        """データセットID処理（DataManagerに委譲）"""
        if hasattr(self.parent, 'data_manager'):
            return self.parent.data_manager.process_dataset_id(
                id=id, 
                name=name, 
                details_dir=details_dir, 
                headers=headers,
                set_webview_message=getattr(self.parent, 'set_webview_message', None),
                fetch_and_save_dataset_detail=self.fetch_and_save_dataset_detail,
                datatree_json_path=getattr(self.parent, 'datatree_json_path', ''),
                save_webview_blob_images=self.save_webview_blob_images,
                image_dir=getattr(self.parent, 'image_dir', '')
            )
        return False

    @debug_log
    def save_webview_blob_images(self, data_id, subdir, headers):
        """WebView blob画像保存（ImageProcessorに委譲）"""
        if hasattr(self.parent, 'image_processor'):
            self.parent.image_processor.save_webview_blob_images(data_id, subdir, headers)

    @debug_log
    def fetch_and_save_multiple_datasets(self, grant_number=None):
        """複数データセット取得・保存処理（DataManagerに委譲）"""
        if hasattr(self.parent, 'data_manager'):
            # コールバック関数を定義
            def fetch_and_save_data_list_with_path(id, subdir, headers):
                return self.parent.data_manager.fetch_and_save_data_list(id, subdir, headers, getattr(self.parent, 'datatree_json_path', ''))
            
            return self.parent.data_manager.fetch_and_save_multiple_datasets(
                grant_number=grant_number or getattr(self.parent, 'grant_number', ''),
                set_webview_message=getattr(self.parent, 'set_webview_message', None),
                datatree_json_path=getattr(self.parent, 'datatree_json_path', ''),
                search_result_path=getattr(self.parent, 'search_result_path', ''),
                details_dir=getattr(self.parent, 'details_dir', ''),
                extract_ids_and_names=self.parent.data_manager.extract_ids_and_names,
                parse_cookies_txt=getattr(self.parent, 'parse_cookies_txt', None),
                COOKIE_FILE_RDE=getattr(self.parent, 'COOKIE_FILE_RDE', ''),
                bearer_token=getattr(self.parent, 'bearer_token', ''),
                build_headers=self.parent.data_manager.build_headers,
                process_dataset_id=lambda id, name, details_dir, headers: self.process_dataset_id(
                    id, name, details_dir, headers, fetch_and_save_data_list=fetch_and_save_data_list_with_path
                ),
                apply_arim_anonymization=lambda details_dir, grant_number: self.apply_arim_anonymization(details_dir, grant_number)
            )
        return False

    @debug_log
    def search_and_save_result(self, grant_number=None):
        """API検索・保存処理（DataManagerに委譲）"""
        if hasattr(self.parent, 'data_manager'):
            return self.parent.data_manager.search_and_save_result(
                grant_number=grant_number or getattr(self.parent, 'grant_number', ''),
                bearer_token=getattr(self.parent, 'bearer_token', ''),
                set_webview_message=getattr(self.parent, 'set_webview_message', None)
            )
        return False

    @debug_log
    def fetch_and_save_multiple_datasets(self, grant_number=None):
        """複数データセット取得・保存処理（統合実装）"""
        if not hasattr(self.parent, 'data_manager'):
            return False
            
        # 必要なインポートとパス設定
        from functions.common_funcs import parse_cookies_txt
        from config.common import get_dynamic_file_path, DATATREE_FILE_NAME, get_cookie_file_path
        import os
        
        # grant_numberが指定されていない場合は現在のgrant_numberを使用
        if grant_number is None:
            grant_number = getattr(self.parent, 'grant_number', '')
        
        search_result_path = get_dynamic_file_path(f"output/search_results/{grant_number}.json")
        details_dir = get_dynamic_file_path(f"output/datasets/{grant_number}")
        datatree_json_path = os.path.join(details_dir, DATATREE_FILE_NAME)
        
        # 画像関連の状態をリセット
        if hasattr(self.parent, '_recent_blob_hashes'):
            self.parent._recent_blob_hashes.clear()
        if hasattr(self.parent, '_data_id_image_counts'):
            self.parent._data_id_image_counts.clear()
        self.parent.datatree_json_path = datatree_json_path
        logger.debug("_recent_blob_hashesと画像カウンタをリセットしました")
        
        # コールバック関数を定義
        def fetch_and_save_data_list_with_path(id, subdir, headers, datatree_json_path):
            return self.parent.data_manager.fetch_and_save_data_list(id, subdir, headers, datatree_json_path)
        
        # DataManagerに全ての必要な引数を渡して処理を委譲
        return self.parent.data_manager.fetch_and_save_multiple_datasets(
            grant_number=grant_number,
            set_webview_message=getattr(self.parent, 'set_webview_message', None),
            datatree_json_path=datatree_json_path,
            search_result_path=search_result_path,
            details_dir=details_dir,
            extract_ids_and_names=self.parent.data_manager.extract_ids_and_names,
            parse_cookies_txt=parse_cookies_txt,
            COOKIE_FILE_RDE=get_cookie_file_path(),
            bearer_token=getattr(self.parent, 'bearer_token', ''),
            build_headers=self.parent.data_manager.build_headers,
            process_dataset_id=lambda id, name, details_dir, headers: self.process_dataset_id(
                id, name, details_dir, headers, fetch_and_save_data_list=fetch_and_save_data_list_with_path
            ),
            apply_arim_anonymization=lambda details_dir, grant_number: self.apply_arim_anonymization(details_dir, grant_number)
        )

    @debug_log  
    def _hash_blob(self, b64, filename):
        """blob画像ハッシュ計算（ImageProcessorに委譲）"""
        if hasattr(self.parent, 'image_processor'):
            return self.parent.image_processor._hash_blob(b64, filename)
        return None

    @debug_log
    def center_window(self):
        """ウィンドウを画面中央に移動（UIControllerに委譲）"""
        if hasattr(self.parent, 'ui_controller'):
            self.parent.ui_controller.center_window()
