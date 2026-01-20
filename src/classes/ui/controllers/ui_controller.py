"""
UIコントローラークラス - ARIM RDE Tool
Browserクラスから UI制御ロジックを分離
統一メニュー表示・位置固定・フォント自動調整機能・レスポンシブデザイン対応・テキストエリア拡大機能
【注意】バージョン更新時はconfig/common.py のREVISIONも要確認
"""
import logging

from qt_compat.widgets import (
    QVBoxLayout, QWidget
)
from qt_compat.core import QTimer

from config.common import INPUT_DIR, OUTPUT_DIR, SUMMARY_XLSX_PATH, ensure_directory_exists, get_dynamic_file_path
from classes.basic.util.summary_file_utils import list_summary_workbooks
from classes.theme import get_color, ThemeKey
from classes.utils.button_styles import get_grouped_menu_button_style, get_menu_button_style
from classes.utils.dataset_launch_manager import DatasetLaunchManager

# UIControllerCore をインポート
from .ui_controller_core import UIControllerCore
from classes.ai.ui.ui_controller_ai import UIControllerAI  # 新構造に修正
from .ui_controller_data import UIControllerData
from .ui_controller_forms import UIControllerForms

# 分離したダイアログクラスとユーティリティクラスをインポート
from classes.ui.dialogs.ui_dialogs import TextAreaExpandDialog, PopupDialog

# AI機能データ管理クラスをインポート

logger = logging.getLogger(__name__)

class UIController(UIControllerCore):
    """
    v1.9.8: ARIM拡張結合ロジック強化・デバッグ強化
    UIControllerCoreを継承し、UIロジックを実装
    """
    
    def show_error(self, message):
        """エラーメッセージを表示する"""
        try:
            from qt_compat.widgets import QMessageBox
            QMessageBox.critical(self.parent if hasattr(self, 'parent') else None, 
                                "エラー", str(message))
        except Exception as e:
            # フォールバック：ログのみ
            if hasattr(self, 'logger'):
                self.logger.error(f"エラーメッセージ表示失敗: {e}, 元のメッセージ: {message}")
            logger.error("エラー表示失敗: %s, 元のメッセージ: %s", e, message)

    def _schedule_qt_single_shot(self, delay_ms, callback, *, parent=None, key=None):
        """Schedule a Qt single-shot safely.

        - Uses a parented QTimer so it is cancelled on parent destruction.
        - Guards against callbacks running after QObject deletion.
        - Keeps a reference to the QTimer to avoid premature GC.
        """
        if parent is None:
            parent = getattr(self, "parent", None)

        if parent is None:
            try:
                QTimer.singleShot(delay_ms, callback)
            except Exception:
                pass
            return

        try:
            from shiboken6 import isValid

            if not isValid(parent):
                return
        except Exception:
            pass

        timer = QTimer(parent)
        timer.setSingleShot(True)

        store_key = key or f"_rde_single_shot_{id(timer)}"
        if not hasattr(self, "_rde_single_shot_timers"):
            self._rde_single_shot_timers = {}

        self._rde_single_shot_timers[store_key] = timer

        def _on_timeout():
            try:
                try:
                    from shiboken6 import isValid

                    if not isValid(parent):
                        return
                except Exception:
                    pass

                callback()
            except (RuntimeError, AttributeError):
                # QObject deleted / callback no longer valid
                pass
            finally:
                try:
                    self._rde_single_shot_timers.pop(store_key, None)
                except Exception:
                    pass

        try:
            timer.timeout.connect(_on_timeout)
            timer.start(int(delay_ms))
        except Exception:
            try:
                self._rde_single_shot_timers.pop(store_key, None)
            except Exception:
                pass
            return
    
    def show_text_area_expanded(self, text_widget, title):
        """
        テキストエリアの内容を拡大表示（UIControllerFormsに委譲）
        Phase 2 Step 3.2: UI表示層への委譲
        """
        # TODO: 特殊処理（AI問い合わせ結果）が含まれるため、段階的移行
        # 問い合わせ結果の場合はAIコントローラーに委譲
        if title == "問い合わせ結果" and hasattr(self, 'last_response_info') and self.last_response_info:
            return self.ai_controller.show_text_area_with_ai_response_info(text_widget, title)
        
        # その他の場合はforms_controllerに委譲
        if hasattr(self, 'forms_controller') and self.forms_controller:
            return self.forms_controller.show_text_area_expanded(text_widget, title)
        else:
            # フォールバック（旧実装） - TODO: 最終的に削除予定
            try:
                # テキスト内容を取得
                content = ""
                if hasattr(text_widget, 'toPlainText'):
                    content = text_widget.toPlainText()
                    # QTextBrowserの場合、HTMLコンテンツも確認
                    if hasattr(text_widget, 'toHtml') and not content.strip():
                        html_content = text_widget.toHtml()
                        if html_content.strip():
                            content = html_content
                elif hasattr(text_widget, 'toHtml'):
                    content = text_widget.toHtml()
                else:
                    content = str(text_widget)
                
                # コンテンツが空の場合のメッセージ
                if not content.strip():
                    content = "（内容が空です）"
                
                # 編集可能かどうかを判定
                editable = not text_widget.isReadOnly() if hasattr(text_widget, 'isReadOnly') else False
                
                # ダイアログを表示（元のウィジェットへの参照を渡す）
                dialog = TextAreaExpandDialog(self.parent, title, content, editable, text_widget)
                dialog.show()
            
            except Exception as e:
                logger.error("拡大表示エラー: %s", e)
            # エラー時もダイアログを表示
            dialog = TextAreaExpandDialog(self.parent, title, f"エラーが発生しました: {e}", False)
            dialog.show()
    
    def adjust_window_height_to_contents(self):
        """
        メインウィンドウの高さをコンテンツに合わせて自動調整
        画面サイズの95%を上限とし、収まらない場合はスクロールバー対応
        """
        parent = self.parent
        mode = getattr(self, 'current_mode', None)
        
        if not hasattr(parent, 'sizeHint'):
            return
            
        from qt_compat.widgets import QApplication
        
        # 画面サイズを取得
        screen = QApplication.primaryScreen()
        if not screen:
            return
            
        screen_geometry = screen.geometry()
        max_screen_height = int(screen_geometry.height() * 0.90)  # 90%制限
        max_screen_width = int(screen_geometry.width() * 0.90)

        # コンテンツに必要なサイズを計算
        hint = parent.sizeHint()
        
        # モード別の最小サイズ設定
        if mode == "data_register":
            min_height = 600  # データ登録は大きめに
            min_width = 1000
        elif mode == "subgroup_create":
            min_height = 400
            min_width = 900
        elif mode == "data_fetch":
            min_height = 700
            min_width = 1000
        elif mode == "ai_test":
            min_height = 800
            min_width = 1100
        else:
            min_height = 500
            min_width = 900
        
        # 新しいサイズを計算（95%制限内で）
        new_height = max(min_height, min(hint.height(), max_screen_height))
        new_width = max(min_width, min(hint.width(), max_screen_width))
        
        # サイズ制約をクリアして動的リサイズを可能にする
        parent.setMinimumSize(200, 200)
        parent.setMaximumSize(16777215, 16777215)
        
        # ウィンドウをリサイズ
        parent.resize(new_width, new_height)
        
        logger.debug("ウィンドウ高さ自動調整: %sx%s (画面比率: %.1f%%)", new_width, new_height, new_height/screen_geometry.height()*100)
        
        # スクロールエリア内のウィジェットが画面に収まるようにする
        if hasattr(parent, 'centralWidget'):
            central_widget = parent.centralWidget()
            if central_widget and hasattr(central_widget, 'findChildren'):
                from qt_compat.widgets import QScrollArea
                scroll_areas = central_widget.findChildren(QScrollArea)
                for scroll_area in scroll_areas:
                    if scroll_area.widget():
                        scroll_area.widget().adjustSize()
                        scroll_area.updateGeometry()
    def update_message_labels_position(self, mode):
        """
        autologin_msg_label/webview_msg_labelの位置をメニューごとに動的に再配置
        """
        # 親ウィジェットのレイアウト構造を前提とする
        parent = self.parent
        if not hasattr(parent, 'autologin_msg_label') or not hasattr(parent, 'webview_msg_label'):
            return
        # WebViewが表示されている場合はwebview_widget直下に詰めて表示
        if hasattr(parent, 'webview') and parent.webview.isVisible():
            # webview_widgetのvboxレイアウトを取得
            webview_widget = parent.findChild(QWidget, 'webview_widget')
            vbox = None
            if webview_widget:
                vbox = webview_widget.layout()
            # fallback: 直接親レイアウトを取得
            if vbox is None and hasattr(parent, 'webview'):
                vbox = parent.webview.parentWidget().layout()
            # 既存のラベルを一度取り除く
            for label in [parent.autologin_msg_label, parent.webview_msg_label]:
                if label.parent() and label.parent().layout():
                    label.parent().layout().removeWidget(label)
            # WebView直下に追加
            if vbox:
                vbox.addWidget(parent.autologin_msg_label)
                vbox.addWidget(parent.webview_msg_label)
        else:
            # WebView非表示時はmenu_area_layoutの一番上に追加
            if hasattr(parent, 'menu_area_layout'):
                for label in [parent.autologin_msg_label, parent.webview_msg_label]:
                    if label.parent() and label.parent().layout():
                        label.parent().layout().removeWidget(label)
                parent.menu_area_layout.insertWidget(0, parent.webview_msg_label)
                parent.menu_area_layout.insertWidget(0, parent.autologin_msg_label)
    def on_webview_login_success(self):
        """
        ログイン完了時にWebView/オーバーレイを小さくする
        """
        if hasattr(self.parent, 'webview'):
            self.parent.webview.setVisible(True)
            # NOTE:
            # QWebEngineView を固定サイズにすると、レイアウトの余白や未描画領域が
            # 黒く見える（プラットフォーム依存）/overlayの重なりが不正になることがある。
            # ここでは「固定サイズ」を廃止し、通常のレイアウト伸縮に任せる。
            try:
                from qt_compat.widgets import QSizePolicy
                self.parent.webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            except Exception:
                pass
            try:
                self.parent.webview.setMinimumSize(800, 500)
            except Exception:
                pass
        if hasattr(self.parent, 'overlay_manager'):
            self.parent.overlay_manager.resize_overlay()
            # オーバーレイはデータ取得モード（data_fetch）のみ表示
            current_mode = getattr(self, 'current_mode', None)
            if current_mode == "data_fetch":
                self.parent.overlay_manager.show_overlay()
            else:
                self.parent.overlay_manager.hide_overlay()
    
    def on_login_complete(self):
        """
        ログイン完了時の処理（両トークン取得完了）
        全機能ボタンを有効化し、待機メッセージを3秒後に非表示にする
        v2.0.2: メッセージを即座に非表示せず、成功メッセージを表示
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info("[UI] ログイン完了 - 全機能ボタンを有効化")

        # 性能計測: ログイン完了時点でサマリを出力（有効時のみ）
        try:
            from classes.utils.perf_monitor import PerfMonitor

            perf_logger = logging.getLogger("RDE_WebView")
            PerfMonitor.mark("login:complete", logger=perf_logger)
            PerfMonitor.dump_summary(logger=perf_logger, top=15)
        except Exception:
            pass
        
        # 全ボタンを有効化
        if hasattr(self, 'menu_buttons'):
            for mode, button in self.menu_buttons.items():
                if button and hasattr(button, 'setEnabled'):
                    button.setEnabled(True)
                    logger.debug(f"[UI] {mode}ボタンを有効化")
        
        # 待機メッセージを3秒後に非表示（成功メッセージを見せるため）
        if hasattr(self.parent, 'autologin_msg_label'):
            # 3秒後に非表示
            self._schedule_qt_single_shot(3000, self._hide_login_message_safely, key="hide_login_message")
    
    def _hide_login_message_safely(self):
        """ログインメッセージを安全に非表示"""
        try:
            if hasattr(self.parent, 'autologin_msg_label'):
                self.parent.autologin_msg_label.setVisible(False)
        except RuntimeError:
            # オブジェクトが削除済みの場合は無視
            pass

    
    def set_buttons_enabled_except_login_settings(self, enabled: bool):
        """
        ログイン・設定ボタン以外の有効/無効を設定
        
        Args:
            enabled: Trueで有効化、Falseで無効化
        
        Note:
            DEBUG_SKIP_LOGIN_CHECK環境変数が設定されている場合、
            無効化リクエストを無視して常に有効化します（デバッグ用）
        """
        import logging
        import os
        logger = logging.getLogger(__name__)
        
        # デバッグモード確認
        debug_skip = os.environ.get('DEBUG_SKIP_LOGIN_CHECK', '').lower() in ('1', 'true', 'yes')
        if debug_skip and not enabled:
            logger.warning("[DEBUG] DEBUG_SKIP_LOGIN_CHECK有効 - ボタン無効化リクエストを無視")
            enabled = True  # 強制的に有効化
        
        logger.info(f"[UI] ボタン有効化状態変更: {enabled}")
        
        if not hasattr(self, 'menu_buttons'):
            return
        
        # ログイン、設定、ヘルプは常に有効
        exclude_modes = {'login', 'settings', 'help'}
        for mode, button in self.menu_buttons.items():
            if mode not in exclude_modes and button and hasattr(button, 'setEnabled'):
                button.setEnabled(enabled)
                logger.debug(f"[UI] {mode}ボタンを{'有効' if enabled else '無効'}化")

    def on_attachment_file_select_clicked(self):
        """
        添付ファイル選択ボタン押下時の処理。添付ファイルパスを保存し、登録実行ボタンの有効/無効を制御。
        """
        from qt_compat.widgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(None, "添付ファイルを選択", "", "すべてのファイル (*)")
        if files:
            self.selected_attachment_files = files
            if hasattr(self, 'attachment_file_select_button'):
                self.attachment_file_select_button.setText(f"添付ファイル選択({len(files)}件)")
        else:
            self.selected_attachment_files = []
            if hasattr(self, 'attachment_file_select_button'):
                self.attachment_file_select_button.setText("添付ファイル選択(未選択)")
        self.update_register_exec_button_state()

    def on_sample_selection_changed(self, idx):
        """
        試料選択コンボボックスの変更時処理
        Args:
            idx: 選択されたインデックス
        """
        try:
            if not hasattr(self, 'sample_select_combo'):
                return

            sample_data = self.sample_select_combo.itemData(idx)
            
            if sample_data is None:
                # "新規入力"が選択された場合は入力欄をクリアし、sampleIdもクリア
                self.selected_sample_id = None
                # 入力欄を編集可能にする
                self.set_sample_inputs_enabled(True)
                if hasattr(self, 'sample_names_input'):
                    self.sample_names_input.clear()
                if hasattr(self, 'sample_description_input'):
                    if hasattr(self.sample_description_input, 'clear'):
                        self.sample_description_input.clear()
                    else:
                        self.sample_description_input.setPlainText("")
                if hasattr(self, 'sample_composition_input'):
                    self.sample_composition_input.clear()
            else:
                # 既存試料が選択された場合はsampleIdを保存し、入力欄に値を設定
                self.selected_sample_id = sample_data.get('id')
                attributes = sample_data.get('attributes', {})
                
                # 入力欄を編集不可にする
                self.set_sample_inputs_enabled(False)
                
                if hasattr(self, 'sample_names_input'):
                    # names配列の最初の要素を使用
                    names = attributes.get('names', [])
                    name = names[0] if names else ''
                    self.sample_names_input.setText(name)
                    
                if hasattr(self, 'sample_description_input'):
                    description = attributes.get('description', '')
                    if hasattr(self.sample_description_input, 'setText'):
                        self.sample_description_input.setText(description)
                    else:
                        self.sample_description_input.setPlainText(description)
                    
                if hasattr(self, 'sample_composition_input'):
                    composition = attributes.get('composition', '')
                    self.sample_composition_input.setText(composition)
                    
        except Exception as e:
            if hasattr(self.parent, 'display_manager'):
                self.parent.display_manager.set_message(f"試料選択変更処理エラー: {e}")
            logger.error("試料選択変更処理エラー: %s", e)

    def set_sample_inputs_enabled(self, enabled):
        """
        試料入力フィールドの編集可能状態を設定
        Args:
            enabled: True=編集可能、False=編集不可
        """
        try:
            if hasattr(self, 'sample_names_input'):
                self.sample_names_input.setEnabled(enabled)
            if hasattr(self, 'sample_description_input'):
                self.sample_description_input.setEnabled(enabled)
            if hasattr(self, 'sample_composition_input'):
                self.sample_composition_input.setEnabled(enabled)
        except Exception as e:
            logger.error("試料入力フィールド編集可能状態設定エラー: %s", e)

    def update_register_exec_button_state(self):
        """
        データファイルが選択されていれば登録実行ボタンを有効化（添付ファイルは判定に使わない）
        """
        files = getattr(self, 'selected_register_files', [])
        # 添付ファイルの有無は判定に使わない
        enable = bool(files)
        if hasattr(self, 'register_exec_button'):
            self.register_exec_button.setEnabled(enable)
            
    def prepare_dataset_open_request(self):
        """
        データセット開設ボタン押下時のロジック（UIControllerDataに委譲）
        Phase 2 Step 3.1: データ処理層への委譲
        """
        # TODO: 旧実装を新実装（data_controller委譲）に完全移行後、このコメントを削除
        if hasattr(self, 'data_controller') and self.data_controller:
            return self.data_controller.prepare_dataset_open_request()
        else:
            # フォールバック（旧実装） - TODO: 最終的に削除予定
            try:
                from classes.dataset.core.dataset_open_logic import run_dataset_open_logic  # 新構造に修正
                bearer_token = getattr(self.parent, 'bearer_token', None)
                run_dataset_open_logic(parent=None, bearer_token=bearer_token)
            except Exception as e:
                from qt_compat.widgets import QMessageBox
                QMessageBox.warning(None, "エラー", f"データセット開設ロジック呼び出し失敗: {e}")
                if hasattr(self.parent, 'display_manager'):
                    self.parent.display_manager.set_message(f"データセット開設ロジック呼び出し失敗: {e}")

    def on_file_select_clicked(self):
        """
        ファイル選択ボタン押下時の処理。ファイルパスを保存し、登録実行ボタンの有効/無効を制御。
        """
        from qt_compat.widgets import QFileDialog
        files, _ = QFileDialog.getOpenFileNames(None, "登録するファイルを選択", "", "すべてのファイル (*)")
        if files:
            self.selected_register_files = files
            self.selected_file_path = files[0] if files else None  # 互換性のため最初のファイルを設定
            if hasattr(self, 'file_select_button'):
                self.file_select_button.setText(f"ファイル選択({len(files)}件)")
        else:
            self.selected_register_files = []
            self.selected_file_path = None
            if hasattr(self, 'file_select_button'):
                self.file_select_button.setText("ファイル選択(未選択)")
        self.update_register_exec_button_state()

    def on_register_exec_clicked(self):
        """
        登録実行ボタン押下時の処理。ファイルパスをrun_data_register_logicに渡す。
        カスタム欄（スキーマフォーム）の値もpayloadに反映する。
        """
        try:
            # まず早期バリデーションを実行
            if not self.validate_sample_info_early():
                return  # バリデーション失敗時は処理を停止
                
            from classes.data_entry.core.data_register_logic import run_data_register_logic
            bearer_token = getattr(self.parent, 'bearer_token', None)
            dataset_info = None
            combo = None
            if hasattr(self, 'dataset_dropdown') and self.dataset_dropdown is not None:
                # dataset_dropdownがQWidgetラッパーの場合は中のQComboBoxを参照
                if hasattr(self.dataset_dropdown, 'dataset_dropdown'):
                    combo = self.dataset_dropdown.dataset_dropdown
                elif hasattr(self.dataset_dropdown, 'currentIndex'):
                    combo = self.dataset_dropdown
            if combo is not None:
                idx = combo.currentIndex()
                dataset_info = combo.itemData(idx, role=0x0100)  # Qt.UserRole

            # 入力値取得
            form_values = {}
            if hasattr(self, 'data_name_input'):
                form_values['dataName'] = self.data_name_input.text()
            if hasattr(self, 'basic_description_input'):
                # QTextEditの場合はtoPlainText()
                desc_widget = self.basic_description_input
                if hasattr(desc_widget, 'toPlainText'):
                    form_values['basicDescription'] = desc_widget.toPlainText()
                else:
                    form_values['basicDescription'] = desc_widget.text()
            if hasattr(self, 'experiment_id_input'):
                form_values['experimentId'] = self.experiment_id_input.text()
            if hasattr(self, 'data_owner_combo') and self.data_owner_combo:
                # データ所有者（所属）の選択値を取得
                selected_owner_id = self.data_owner_combo.currentData()
                if selected_owner_id:
                    form_values['dataOwnerId'] = selected_owner_id
            # 動的フォームから試料情報を取得（新しいフォーム構造対応）
            if hasattr(self, 'sample_input_widgets'):
                # 新しいフォーム構造から取得
                try:
                    # 既存試料選択チェック
                    selected_sample_data = None
                    if hasattr(self, 'sample_combo'):
                        current_index = self.sample_combo.currentIndex()
                        if current_index > 0:  # "新規作成"以外が選択された場合
                            selected_sample_data = self.sample_combo.currentData()
                    
                    if selected_sample_data:
                        # 既存試料選択の場合
                        form_values['sampleId'] = selected_sample_data.get('id')
                        # 既存データから値を設定（表示用ではなくロジック用）
                        names = selected_sample_data.get('names', [])
                        if not names and selected_sample_data.get('name'):
                            names = [selected_sample_data.get('name')]
                        form_values['sampleNames'] = names
                        
                        form_values['sampleDescription'] = selected_sample_data.get('description', '')
                        form_values['sampleComposition'] = selected_sample_data.get('composition', '')
                        form_values['sampleReferenceUrl'] = selected_sample_data.get('referenceUrl', '')
                        tags = selected_sample_data.get('tags', [])
                        form_values['sampleTags'] = tags
                        form_values['ownerId'] = selected_sample_data.get('ownerId')
                        form_values['hideOwner'] = selected_sample_data.get('hideOwner', False)
                        form_values['relatedSamples'] = selected_sample_data.get('relatedSamples', [])
                    else:
                        # 新規試料作成の場合
                        if 'name' in self.sample_input_widgets:
                            # SampleNamesWidgetからリストを取得
                            names = self.sample_input_widgets['name'].get_sample_names()
                            form_values['sampleNames'] = names
                        if 'description' in self.sample_input_widgets:
                            form_values['sampleDescription'] = self.sample_input_widgets['description'].toPlainText()
                        if 'composition' in self.sample_input_widgets:
                            form_values['sampleComposition'] = self.sample_input_widgets['composition'].text()
                        if 'url' in self.sample_input_widgets:
                            form_values['sampleReferenceUrl'] = self.sample_input_widgets['url'].text()
                        if 'tags' in self.sample_input_widgets:
                            # タグはカンマ区切り文字列で入力されるが、ここでリスト化してもよいし、ロジック側で処理してもよい。
                            # 既存ロジックに合わせて文字列のまま渡すか、リストにするか。
                            # ここでは文字列のまま渡して、ロジック側で柔軟に対応するようにする。
                            form_values['sampleTags'] = self.sample_input_widgets['tags'].text()
                        if 'manager' in self.sample_input_widgets:
                            form_values['ownerId'] = self.sample_input_widgets['manager'].currentData()
                        if 'hide_owner' in self.sample_input_widgets:
                            form_values['hideOwner'] = self.sample_input_widgets['hide_owner'].isChecked()
                        if 'related_samples' in self.sample_input_widgets:
                            form_values['relatedSamples'] = self.sample_input_widgets['related_samples'].get_related_samples()
                except Exception as e:
                    logger.error("新しいフォーム構造から試料データ取得エラー: %s", e)
            else:
                # 旧フォーム構造から取得（互換性維持）
                if hasattr(self, 'sample_description_input'):
                    if hasattr(self.sample_description_input, 'toPlainText'):
                        # QTextEditの場合
                        form_values['sampleDescription'] = self.sample_description_input.toPlainText()
                    else:
                        # QLineEditの場合
                        form_values['sampleDescription'] = self.sample_description_input.text()
                if hasattr(self, 'sample_composition_input'):
                    form_values['sampleComposition'] = self.sample_composition_input.text()
                if hasattr(self, 'sample_names_input'):
                    form_values['sampleNames'] = self.sample_names_input.text()
                # 既存試料が選択されている場合はsampleIdを設定
                if hasattr(self, 'selected_sample_id') and self.selected_sample_id:
                    form_values['sampleId'] = self.selected_sample_id
            
            # その他の項目（参考URL、タグなど）
            if hasattr(self, 'sample_reference_url_input'):
                form_values['sampleReferenceUrl'] = self.sample_reference_url_input.text()
            if hasattr(self, 'sample_tags_input'):
                form_values['sampleTags'] = self.sample_tags_input.text()

            # カスタム欄（スキーマフォーム）の値を取得（英語keyで）
            if hasattr(self, 'schema_form_widget') and self.schema_form_widget is not None:
                custom_values = {}
                key_to_widget = getattr(self.schema_form_widget, '_schema_key_to_widget', {})
                for key, widget in key_to_widget.items():
                    value = None
                    if hasattr(widget, 'currentText'):
                        value = widget.currentText()
                    elif hasattr(widget, 'text'):
                        value = widget.text()
                    custom_values[key] = value
                form_values['custom'] = custom_values

            file_paths = getattr(self, 'selected_register_files', None)
            attachment_paths = getattr(self, 'selected_attachment_files', None)
            if not file_paths:
                from qt_compat.widgets import QMessageBox
                QMessageBox.warning(None, "エラー", "データファイルが選択されていません。")
                return

            # 通常登録の進捗ダイアログは「確認」押下まで閉じない仕様。
            # parent=None だと参照切れで自動クローズすることがあるため、親ウィンドウを渡す。
            parallel_workers = 5
            try:
                spin = getattr(self, 'parallel_upload_spinbox', None)
                if spin is not None:
                    parallel_workers = int(spin.value())
            except Exception:
                parallel_workers = 5

            result = run_data_register_logic(
                parent=self.parent,
                bearer_token=bearer_token,
                dataset_info=dataset_info,
                form_values=form_values,
                file_paths=file_paths,
                attachment_paths=attachment_paths,
                parallel_upload_workers=parallel_workers,
            )
            # 成功時ステータスダイアログ表示（最新1件確認）
            try:
                if result and isinstance(result, dict) and result.get('success'):
                    # create_entry.json の内容を利用可能なら読み込み
                    from config.common import get_dynamic_file_path
                    import json, os
                    entry_json_path = get_dynamic_file_path('output/rde/create_entry.json')
                    data_item = None
                    if os.path.exists(entry_json_path):
                        with open(entry_json_path, 'r', encoding='utf-8') as f:
                            created_data = json.load(f)
                            # RDEエントリー生成レスポンスの簡易抽出
                            entry = (created_data.get('data') or {}) if isinstance(created_data, dict) else {}
                            eid = entry.get('id') or 'NEW'
                            attrs = entry.get('attributes') or {}
                            invoice = attrs.get('invoice') or {}
                            basic = invoice.get('basic') or {}
                            sample = invoice.get('sample') or {}
                            data_name = basic.get('dataName') or form_values.get('dataName')
                            created_ts = sample.get('created') or basic.get('dateSubmitted')  # 優先: sample.created
                            instrument_id = basic.get('instrumentId') or ''
                            owner_id = basic.get('dataOwnerId') or ''
                            data_item = {
                                'id': eid,
                                'attributes': {
                                    'name': data_name,
                                    'created': created_ts or ''
                                },
                                'relationships': {
                                    'owner': {'data': {'id': owner_id}},
                                    'instrument': {'data': {'id': instrument_id}} if instrument_id else {}
                                }
                            }
                    if not data_item:
                        # フォールバック（レスポンス未解析）: 入力値と現在時刻で擬似作成
                        import datetime as _dt
                        data_item = {
                            'id': 'NEW',
                            'attributes': {
                                'name': form_values.get('dataName') or '',
                                'created': _dt.datetime.utcnow().isoformat() + 'Z'
                            },
                            'relationships': {
                                'owner': {'data': {'id': ''}},
                                'instrument': {}
                            }
                        }
                    # タブウィジェット経由でダイアログ表示
                    try:
                        if hasattr(self.parent, 'data_register_tab_widget'):
                            self.parent.data_register_tab_widget.show_status_after_single(data_item)
                    except Exception as se:
                        logger.warning(f"登録後ステータスダイアログ表示失敗: {se}")
            except Exception as ie:
                logger.warning(f"登録後ステータス処理例外: {ie}")
        except Exception as e:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(None, "エラー", f"データ登録ロジック呼び出し失敗: {e}")
            if hasattr(self.parent, 'display_manager'):
                self.parent.display_manager.set_message(f"データ登録ロジック呼び出し失敗: {e}")

    def prepare_settings_request(self):
        """
        設定ボタン押下時のロジック（新構造対応）
        bearer_tokenを渡してプロキシ設定等を起動
        """
        try:
            # 新構造の設定ロジックを呼び出し
            from classes.config.core.settings_logic import run_settings_logic
            bearer_token = getattr(self.parent, 'bearer_token', None)
            run_settings_logic(parent=self.parent, bearer_token=bearer_token)
            
            # ステータス表示
            if hasattr(self.parent, 'display_manager'):
                self.parent.display_manager.set_message("設定画面を起動しました")
                
        except ImportError as e:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(None, "設定エラー", f"設定モジュールの読み込みに失敗しました: {e}")
            if hasattr(self.parent, 'display_manager'):
                self.parent.display_manager.set_message(f"設定モジュール読み込み失敗: {e}")
                
        except Exception as e:
            from qt_compat.widgets import QMessageBox
            QMessageBox.warning(None, "エラー", f"設定ロジック呼び出し失敗: {e}")
            if hasattr(self.parent, 'display_manager'):
                self.parent.display_manager.set_message(f"設定ロジック呼び出し失敗: {e}")
    """UI制御を担当するクラス"""
    
    def __init__(self, parent_widget):
        """
        UIコントローラーの初期化
        Args:
            parent_widget: 親ウィジェット（Browserクラスのインスタンス）
        """
        # 親クラス（UIControllerCore）の初期化を呼び出し
        super().__init__(parent_widget)
        
        # Bearer token プロパティを追加
        self._bearer_token = None
        
        # AI機能コントローラーを初期化
        self.ai_controller = UIControllerAI(self)
        
        # データ機能コントローラーを初期化
        self.data_controller = UIControllerData(self)
        
        # フォーム機能コントローラーを初期化
        self.forms_controller = UIControllerForms(self)

        # データセット連携マネージャーへUIコントローラーを登録
        DatasetLaunchManager.instance().set_ui_controller(self)

        # --- request_analyzer: WebView signal connection flags ---
        # disconnect() on an unconnected signal emits RuntimeWarning on some PySide builds.
        self._request_analyzer_webview_monitoring_connected = False
        self._request_analyzer_overlay_prevention_connected = False

        # Heavy UI preloads (improves "first click" latency)
        self._ai_suggestion_dialog_cls = None

        # テスト実行中はタイミングが不安定になりやすいため自動プリロードしない
        try:
            import os

            if not os.environ.get("PYTEST_CURRENT_TEST"):
                self._schedule_qt_single_shot(
                    1500,
                    self.preload_ai_suggestion_dialog,
                    parent=self.parent,
                    key="preload_ai_suggestion_dialog",
                )
        except Exception:
            pass

    def preload_ai_suggestion_dialog(self) -> None:
        """Preload heavy AI dialog module to reduce first-open latency."""
        try:
            self._get_ai_suggestion_dialog_class()
        except Exception:
            # 失敗しても実運用に影響させない
            pass

    def _get_ai_suggestion_dialog_class(self):
        if self._ai_suggestion_dialog_cls is not None:
            return self._ai_suggestion_dialog_cls
        from classes.dataset.ui.ai_suggestion_dialog import AISuggestionDialog

        self._ai_suggestion_dialog_cls = AISuggestionDialog
        return AISuggestionDialog
    
    @property
    def bearer_token(self):
        """Bearer token を取得"""
        if self._bearer_token:
            return self._bearer_token
        # parentからbearer_tokenを取得を試行
        if hasattr(self, 'parent') and hasattr(self.parent, 'bearer_token'):
            return self.parent.bearer_token
        return None
    
    @bearer_token.setter
    def bearer_token(self, value):
        """Bearer token を設定"""
        self._bearer_token = value
        # トークン更新時に、すでに初期化済みのタブwidgetも更新
        self._update_tabs_bearer_token(value)
    
    def _update_tabs_bearer_token(self, token):
        """
        全タブwidgetのbearer_tokenを更新
        
        Args:
            token: 新しいトークン
        """
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[TOKEN] 全タブwidgetのbearer_token更新開始: token={token[:20] if token else 'None'}...")
            
            updated_count = 0
            
            # 各タブwidgetの属性をチェックして更新
            if hasattr(self, '_dataset_tab_widget'):
                logger.debug(f"[TOKEN] _dataset_tab_widget存在: {self._dataset_tab_widget is not None}")
                if self._dataset_tab_widget and hasattr(self._dataset_tab_widget, 'bearer_token'):
                    self._dataset_tab_widget.bearer_token = token
                    logger.info("[TOKEN] dataset_tab_widgetを更新")
                    updated_count += 1
            else:
                logger.debug("[TOKEN] _dataset_tab_widget属性が存在しません")
            
            # data_fetch2関連
            if hasattr(self.parent, 'data_fetch2_widget'):
                logger.debug(f"[TOKEN] data_fetch2_widget存在: {self.parent.data_fetch2_widget is not None}")
                if self.parent.data_fetch2_widget and hasattr(self.parent.data_fetch2_widget, 'bearer_token'):
                    self.parent.data_fetch2_widget.bearer_token = token
                    logger.info("[TOKEN] data_fetch2_widgetを更新")
                    updated_count += 1
            else:
                logger.debug("[TOKEN] data_fetch2_widget属性が存在しません")
            
            # 設定widget
            if hasattr(self, '_settings_widget'):
                logger.debug(f"[TOKEN] _settings_widget存在: {self._settings_widget is not None}")
                if self._settings_widget and hasattr(self._settings_widget, 'bearer_token'):
                    self._settings_widget.bearer_token = token
                    logger.info("[TOKEN] settings_widgetを更新")
                    updated_count += 1
            else:
                logger.debug("[TOKEN] _settings_widget属性が存在しません")
                    
            logger.info(f"[TOKEN] 全タブwidgetのbearer_token更新完了: {updated_count}個のwidgetを更新")
            
        except Exception as e:
            logger.error(f"[TOKEN] タブwidget更新エラー: {e}", exc_info=True)
    
    @property 
    def webview(self):
        """WebViewインスタンスを取得"""
        if hasattr(self, 'parent') and hasattr(self.parent, 'webview'):
            return self.parent.webview
        return None
        
    def update_sample_form(self, group_id, widget, layout):
        """
        試料フォーム更新（フォームコントローラーに委譲）
        Args:
            group_id: グループID
            widget: 親ウィジェット
            layout: 親レイアウト
        """
        return self.forms_controller.update_sample_form(group_id, widget, layout)
        
    def validate_sample_info_early(self):
        """
        試料情報早期バリデーション（フォームコントローラーに委譲）
        Returns:
            bool: バリデーション結果
        """
        return self.forms_controller.validate_sample_info_early()
        
    def init_mode_widgets(self):
        """
        モード切り替え用のウィジェットを初期化
        """
        # ボタンスタイルの設定（統一サイズで重なりを防ぐ）
        base_active_style = get_menu_button_style(True)
        base_inactive_style = get_menu_button_style(False)
        button_width = 120  # ボタン幅を統一
        button_height = 32  # ボタン高さを統一

        # ログインメニュー追加（初期アクティブ）
        self.menu_buttons['login'] = self.create_auto_resize_button(
            'ログイン', button_width, button_height, base_active_style
        )
        self.menu_buttons['login'].clicked.connect(
            lambda: self.switch_mode("login")
        )

        self.menu_buttons['subgroup_create'] = self.create_auto_resize_button(
            'サブグループ', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['subgroup_create'].clicked.connect(
            lambda: self.switch_mode("subgroup_create")
        )

        self.menu_buttons['dataset_open'] = self.create_auto_resize_button(
            'データセット', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['dataset_open'].clicked.connect(
            lambda: self.switch_mode("dataset_open")
        )

        self.menu_buttons['data_register'] = self.create_auto_resize_button(
            'データ登録/タイル', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['data_register'].clicked.connect(
            lambda: self.switch_mode("data_register")
        )

        self.menu_buttons['sample_dedup'] = self.create_auto_resize_button(
            '試料', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['sample_dedup'].clicked.connect(
            lambda: self.switch_mode("sample_dedup")
        )

        self.menu_buttons['data_fetch2'] = self.create_auto_resize_button(
            'データ取得２', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['data_fetch2'].clicked.connect(
            lambda: self.switch_mode("data_fetch2")
        )

        self.menu_buttons['basic_info'] = self.create_auto_resize_button(
            'RDE基本情報', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['basic_info'].clicked.connect(
            lambda: self.switch_mode("basic_info")
        )

        self.menu_buttons['data_portal'] = self.create_auto_resize_button(
            'データポータル', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['data_portal'].clicked.connect(
            lambda: self.switch_mode("data_portal")
        )

        self.menu_buttons['ai_test2'] = self.create_auto_resize_button(
            'AIテスト2', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['ai_test2'].clicked.connect(
            lambda: self.open_ai_extension_dialog_from_menu()
        )

        self.menu_buttons['settings'] = self.create_auto_resize_button(
            '設定', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['settings'].clicked.connect(
            lambda: self.switch_mode("settings")
        )

        # Optional/hidden-by-default menus (keep available via config)
        self.menu_buttons['data_fetch'] = self.create_auto_resize_button(
            'データ取得', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['data_fetch'].clicked.connect(
            lambda: self.switch_mode("data_fetch")
        )
        self.menu_buttons['ai_test'] = self.create_auto_resize_button(
            'AIテスト', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['ai_test'].clicked.connect(
            lambda: self.switch_mode("ai_test")
        )
        self.menu_buttons['request_analyzer'] = self.create_auto_resize_button(
            'リクエスト解析', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['request_analyzer'].clicked.connect(
            lambda: self.switch_mode("request_analyzer")
        )
        
        # ヘルプボタン（閉じるボタンの上に表示）
        self.menu_buttons['help'] = self.create_auto_resize_button(
            'ℹ️ ヘルプ', button_width, button_height, base_inactive_style
        )
        self.menu_buttons['help'].clicked.connect(
            lambda: self.open_help_dialog()
        )

        # メインメニュー表示切替（既定: データ取得/AIテストは非表示）
        try:
            from classes.managers.app_config_manager import get_config_manager

            cfg = get_config_manager()
            show_data_fetch = bool(cfg.get("app.menu.show_data_fetch", False))
            show_ai_test = bool(cfg.get("app.menu.show_ai_test", False))
            show_request_analyzer = bool(cfg.get("app.menu.show_request_analyzer", False))
        except Exception:
            show_data_fetch = False
            show_ai_test = False
            show_request_analyzer = False

        try:
            self.menu_buttons['data_fetch'].setVisible(show_data_fetch)
        except Exception:
            pass
        try:
            self.menu_buttons['ai_test'].setVisible(show_ai_test)
        except Exception:
            pass

        # 既定: リクエスト解析は非表示（必要な場合のみ設定で表示）
        try:
            self.menu_buttons['request_analyzer'].setVisible(show_request_analyzer)
        except Exception:
            pass
        
        return list(self.menu_buttons.values())
    
    def switch_mode(self, mode):
        import os
        import time

        try:
            from classes.utils.qt_paint_perf_probe import QtPaintPerfProbe
        except Exception:
            QtPaintPerfProbe = None

        try:
            from classes.utils.perf_monitor import PerfMonitor
        except Exception:
            PerfMonitor = None

        perf_key = f"ui:switch_mode:{mode}"
        perf_logger = logging.getLogger("RDE_WebView")
        if PerfMonitor is not None:
            PerfMonitor.start(perf_key, logger=perf_logger)
        _t0 = time.perf_counter()

        is_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))

        # --- 機能切替時のサイズ制約 ---
        # WebView(ログイン/データ取得)用途のみ横幅固定・アスペクト比固定。
        # それ以外の通常機能は常にリサイズ可能にする。
        top_level = self.parent if hasattr(self, 'parent') else None
        if top_level:
            try:
                if mode in {"login", "data_fetch"}:
                    webview_width = getattr(top_level, '_webview_fixed_width', 900)
                    menu_width = 120
                    margin = 40
                    fixed_width = webview_width + menu_width + margin
                    if hasattr(top_level, 'setFixedWidth'):
                        top_level.setFixedWidth(fixed_width)
                    if hasattr(top_level, '_fixed_aspect_ratio'):
                        if hasattr(top_level, 'height') and top_level.height() != 0:
                            top_level._fixed_aspect_ratio = fixed_width / top_level.height()
                        else:
                            top_level._fixed_aspect_ratio = 1.0
                else:
                    # 横幅固定・アスペクト比固定を解除（幅が「元に戻る」症状の根本対策）
                    if hasattr(top_level, '_fixed_aspect_ratio'):
                        top_level._fixed_aspect_ratio = None
                    if hasattr(top_level, 'setMinimumSize'):
                        top_level.setMinimumSize(200, 200)
                    if hasattr(top_level, 'setMaximumSize'):
                        top_level.setMaximumSize(16777215, 16777215)
                    if hasattr(top_level, 'setMinimumWidth'):
                        top_level.setMinimumWidth(200)
                    if hasattr(top_level, 'setMaximumWidth'):
                        top_level.setMaximumWidth(16777215)
                    if hasattr(top_level, 'showNormal'):
                        top_level.showNormal()
            except Exception:
                pass



        should_recreate_dataset_widget = mode == "dataset_open"

        """
        モード切り替え処理
        Args:
            mode: 切り替え先のモード ('data_fetch', 'dataset_open', 'data_register', 'settings')

        # データセットボタン押下時はウィジェットを再生成するために破棄
        if mode == "dataset_open":
            self._dispose_dataset_open_widget()
        """

        # WebView関連の初期化（モード間移動時のデザイン崩れを防止）
        # pytest中はWindows上で不安定化することがあるため、可視状態の強制切替を避ける
        if not is_pytest:
            if hasattr(self.parent, 'autologin_msg_label'):
                self.parent.autologin_msg_label.setVisible(False)
            if hasattr(self.parent, 'webview_msg_label'):
                self.parent.webview_msg_label.setVisible(False)
        
        # オーバーレイは「WebViewが見えている間」に先に剥がす
        # （Windows+WebEngineで、hidden後のrunJavaScriptが不安定になる環境があるため）
        if hasattr(self.parent, 'overlay_manager'):
            self.parent.overlay_manager.hide_overlay()

        # WebViewとwebview_widgetの状態を一旦リセット
        if hasattr(self.parent, 'webview'):
            self.parent.webview.setVisible(False)
            # NOTE: forcing fixedHeight(0) can destabilize QWebEngineView on Windows.
            # Invisible widgets already collapse in layouts.

        webview_widget = self.parent.findChild(QWidget, 'webview_widget')
        if webview_widget:
            webview_widget.setVisible(False)
            # NOTE: keep size constraints untouched; visibility is enough.

        # 右側レイアウト（webview_widget / menu_area_widget）の伸長配分を調整
        # WebViewを非表示にしたモードでは menu_area_widget が全高を使えるようにする
        try:
            right_widget = self.parent.findChild(QWidget, 'right_widget')
            if right_widget and hasattr(right_widget, 'layout'):
                right_layout = right_widget.layout()
                if right_layout and hasattr(right_layout, 'setStretchFactor'):
                    menu_area_widget = getattr(self.parent, 'menu_area_widget', None)
                    if webview_widget and menu_area_widget:
                        right_layout.setStretchFactor(webview_widget, 0)
                        right_layout.setStretchFactor(menu_area_widget, 1)
        except Exception:
            pass

        # 前のモードがリクエスト解析だった場合はクリーンアップ
        if self.current_mode == "request_analyzer":
            self.cleanup_request_analyzer_mode()

        self.current_mode = mode
        # Keep parent (Browser) mode in sync.
        # Menu buttons often call UIController.switch_mode() directly, bypassing Browser.switch_mode().
        try:
            if hasattr(self.parent, "current_mode"):
                self.parent.current_mode = mode
        except Exception:
            pass
        self.update_menu_button_styles(mode)

        # タブ統合機能がある場合はタブの状態も更新
        if hasattr(self.parent, 'tab_integrator'):
            try:
                self.parent.tab_integrator.update_current_mode(mode)
            except Exception as e:
                logger.error("タブ統合機能の更新エラー: %s", e)

        # メニューエリアの更新
        if hasattr(self.parent, 'menu_area_layout'):
            # 既存のウィジェットをすべて削除
            for i in reversed(range(self.parent.menu_area_layout.count())):
                child = self.parent.menu_area_layout.takeAt(i)
                if child.widget():
                    child.widget().setParent(None)

            if should_recreate_dataset_widget:
                self._dispose_dataset_open_widget()

            # 対応するウィジェットを表示
            widget = self.get_mode_widget(mode)
            if widget:
                try:
                    from qt_compat.widgets import QSizePolicy
                    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                except Exception:
                    pass

                # 縦方向に確実に伸長させる（内容が少ない場合でもタブ領域がウィンドウ高を使う）
                try:
                    self.parent.menu_area_layout.addWidget(widget, 1)
                except Exception:
                    self.parent.menu_area_layout.addWidget(widget)

                # 描画の「初回Paint」と「収束」を計測（ロジック完了後も描画が続くケースの切り分け）
                if (
                    QtPaintPerfProbe is not None
                    and PerfMonitor is not None
                    and PerfMonitor.is_enabled(perf_logger)
                ):
                    try:
                        if not hasattr(self, "_qt_paint_perf_probes"):
                            self._qt_paint_perf_probes = []

                        label = f"mode:{mode}"

                        def _on_finished(probe):
                            try:
                                self._qt_paint_perf_probes.remove(probe)
                            except Exception:
                                pass

                        probe = QtPaintPerfProbe(
                            widget,
                            label=label,
                            logger=perf_logger,
                            # UIが「じわじわ」変化するケース（遅延更新が秒単位で飛ぶ）では
                            # settle_ms が短いと早期に settled 扱いになってしまうため長めに取る。
                            settle_ms=1000,
                            timeout_ms=15000,
                            switch_t0=_t0,
                            on_finished=_on_finished,
                        )
                        if probe.start():
                            self._qt_paint_perf_probes.append(probe)
                    except Exception:
                        pass

        # --- WebView/オーバーレイの表示・非表示とサイズ切替 ---
        if mode == "login":
            # ログインモード：WebViewを表示してログインページを読み込む（オーバーレイは非表示）
            
            # ウィンドウサイズを確実に標準サイズに復元
            if top_level:
                webview_width = getattr(top_level, '_webview_fixed_width', 900)
                menu_width = 120
                margin = 40
                fixed_width = webview_width + menu_width + margin
                if hasattr(top_level, 'setFixedWidth'):
                    top_level.setFixedWidth(fixed_width)
                if hasattr(top_level, 'setMinimumSize'):
                    top_level.setMinimumSize(fixed_width, 200)
                if hasattr(top_level, 'setMaximumSize'):
                    top_level.setMaximumSize(fixed_width, 16777215)
            
            if hasattr(self.parent, 'webview'):
                self.parent.webview.setVisible(True)
                try:
                    from qt_compat.widgets import QSizePolicy
                    self.parent.webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    self.parent.webview.setMinimumSize(600, 300)
                    self.parent.webview.setMaximumSize(16777215, 16777215)
                except Exception:
                    pass
                # ログインURLを毎回読み込む
                from config.site_rde import URLS
                from qt_compat.core import QUrl
                self.parent.webview.setUrl(QUrl(URLS["web"]["login"]))
            webview_widget = self.parent.findChild(QWidget, 'webview_widget')
            if webview_widget:
                webview_widget.setVisible(True)
                webview_widget.setMinimumHeight(200)
                webview_widget.setMaximumHeight(16777215)

            # login はWebViewを主役に戻す
            try:
                right_widget = self.parent.findChild(QWidget, 'right_widget')
                if right_widget and hasattr(right_widget, 'layout'):
                    right_layout = right_widget.layout()
                    if right_layout and hasattr(right_layout, 'setStretchFactor'):
                        menu_area_widget = getattr(self.parent, 'menu_area_widget', None)
                        if webview_widget and menu_area_widget:
                            right_layout.setStretchFactor(webview_widget, 3)
                            right_layout.setStretchFactor(menu_area_widget, 1)
            except Exception:
                pass
            if hasattr(self.parent, 'overlay_manager'):
                self.parent.overlay_manager.hide_overlay()
            
            # loginモードでは上部メッセージラベルを再表示
            if not is_pytest:
                if hasattr(self.parent, 'autologin_msg_label'):
                    self.parent.autologin_msg_label.setVisible(True)
                if hasattr(self.parent, 'webview_msg_label'):
                    self.parent.webview_msg_label.setVisible(True)
            
                # ログインコントロールウィジェットを表示
                if hasattr(self.parent, 'login_control_widget'):
                    self.parent.login_control_widget.setVisible(True)
                    self.parent.login_control_widget.update_autologin_button_state()
                
        elif mode in ["subgroup_create", "basic_info", "dataset_open", "data_register", "settings", "ai_test", "data_fetch2", "data_portal", "help"]:
            # WebView本体を非表示
            if hasattr(self.parent, 'webview'):
                self.parent.webview.setVisible(False)
            
            # ログインコントロールウィジェットを非表示
            if hasattr(self.parent, 'login_control_widget'):
                self.parent.login_control_widget.setVisible(False)
            
            # WebViewを含むWidgetも非表示・高さ0
            webview_widget = self.parent.findChild(QWidget, 'webview_widget')
            if webview_widget:
                webview_widget.setVisible(False)
                # NOTE: visibility is enough; avoid fixedHeight(0).

            # 設定/各機能モードでは menu_area_widget を全高に
            try:
                right_widget = self.parent.findChild(QWidget, 'right_widget')
                if right_widget and hasattr(right_widget, 'layout'):
                    right_layout = right_widget.layout()
                    if right_layout and hasattr(right_layout, 'setStretchFactor'):
                        menu_area_widget = getattr(self.parent, 'menu_area_widget', None)
                        if webview_widget and menu_area_widget:
                            right_layout.setStretchFactor(webview_widget, 0)
                            right_layout.setStretchFactor(menu_area_widget, 1)
            except Exception:
                pass
            if hasattr(self.parent, 'overlay_manager'):
                self.parent.overlay_manager.hide_overlay()

            # Ensure window is resizable (login/data_fetch may have fixed width).
            if top_level:
                try:
                    top_level.setMinimumSize(200, 200)
                except Exception:
                    pass
                try:
                    top_level.setMaximumSize(16777215, 16777215)
                except Exception:
                    pass
                try:
                    top_level.setMinimumWidth(200)
                    top_level.setMaximumWidth(16777215)
                except Exception:
                    pass

            # サブグループ・データセット・基本情報・設定モードは初期高さをディスプレイの90%に設定（後から変更可）
            if mode in ["subgroup_create", "basic_info", "dataset_open", "data_register", "settings", "ai_test", "data_fetch2", "data_portal", "help"]:
                import os

                if not os.environ.get("PYTEST_CURRENT_TEST"):
                    try:
                        from qt_compat.widgets import QApplication
                        screen = QApplication.primaryScreen()
                        if screen:
                            screen_geometry = screen.geometry()
                            max_height = int(screen_geometry.height() * 0.90)
                            if top_level and hasattr(top_level, 'resize'):
                                top_level.resize(top_level.width(), max_height)
                    except Exception as e:
                        logger.debug("初期高さ90%リサイズ失敗: %s", e)

            # データセットは初期幅をディスプレイの75%に設定（後から変更可）
            if mode in [ "dataset_open" ]:
                import os

                if not os.environ.get("PYTEST_CURRENT_TEST"):
                    try:
                        from qt_compat.widgets import QApplication
                        screen = QApplication.primaryScreen()
                        if screen:
                            screen_geometry = screen.geometry()
                            max_width = int(screen_geometry.width() * 0.75)
                            if top_level and hasattr(top_level, 'resize'):
                                top_level.resize(max_width, top_level.height())
                    except Exception as e:
                        logger.debug("初期幅75%リサイズ失敗: %s", e)

        elif mode == "data_fetch":
            # データ取得モード：WebViewを表示してオーバーレイも表示
            # ウィンドウサイズを確実に標準サイズに復元し、初期高さ800pxに設定（後から変更可）
            if top_level:
                webview_width = getattr(top_level, '_webview_fixed_width', 900)
                menu_width = 120
                margin = 40
                fixed_width = webview_width + menu_width + margin
                if hasattr(top_level, 'setFixedWidth'):
                    top_level.setFixedWidth(fixed_width)
                if hasattr(top_level, 'setMinimumSize'):
                    top_level.setMinimumSize(fixed_width, 200)
                if hasattr(top_level, 'setMaximumSize'):
                    top_level.setMaximumSize(fixed_width, 16777215)
                # 初期高さ800pxでリサイズ（最大・最小制約はかけない）
                if hasattr(top_level, 'resize'):
                    top_level.resize(fixed_width, 800)
            
            if hasattr(self.parent, 'webview'):
                self.parent.webview.setVisible(True)
                try:
                    from qt_compat.widgets import QSizePolicy
                    self.parent.webview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    self.parent.webview.setMinimumSize(600, 300)
                    self.parent.webview.setMaximumSize(16777215, 16777215)
                except Exception:
                    pass
            
            # ログインコントロールウィジェットを非表示
            if hasattr(self.parent, 'login_control_widget'):
                self.parent.login_control_widget.setVisible(False)
            
            webview_widget = self.parent.findChild(QWidget, 'webview_widget')
            if webview_widget:
                webview_widget.setVisible(True)
                webview_widget.setMinimumHeight(200)
                webview_widget.setMaximumHeight(16777215)
            if hasattr(self.parent, 'overlay_manager'):
                self.parent.overlay_manager.resize_overlay()
                self.parent.overlay_manager.show_overlay()

            # data_fetch に戻った直後にWebEngineが黒化する環境があるため、
            # 背景色の再適用と再描画を遅延実行して復旧を促す。
            if not is_pytest:
                try:
                    self._schedule_qt_single_shot(0, self._refresh_webview_after_show, key="refresh_webview_after_show")
                except Exception:
                    pass
            
        elif mode == "data_fetch2":
            # データ取得2モード：ブラウザ表示は不要のため完全に非表示
            # WebView本体を非表示
            if hasattr(self.parent, 'webview'):
                self.parent.webview.setVisible(False)
            
            # WebViewを含むWidgetも非表示・高さ0
            webview_widget = self.parent.findChild(QWidget, 'webview_widget')
            if webview_widget:
                webview_widget.setVisible(False)
                # NOTE: visibility is enough; avoid fixedHeight(0).
            
            # オーバーレイも非表示
            if hasattr(self.parent, 'overlay_manager'):
                self.parent.overlay_manager.hide_overlay()
            
            # データ取得2専用の初期高さ600pxでリサイズ（最大・最小制約はかけない）
            if top_level:
                if hasattr(top_level, 'setFixedWidth'):
                    # 幅の固定を解除
                    top_level.setMinimumWidth(200)
                    top_level.setMaximumWidth(16777215)
                if hasattr(top_level, 'setMinimumSize'):
                    top_level.setMinimumSize(200, 200)
                if hasattr(top_level, 'setMaximumSize'):
                    top_level.setMaximumSize(16777215, 16777215)
                if hasattr(top_level, 'resize'):
                    # 初期高さ600px
                    top_level.resize(top_level.width(), 600)
            
        elif mode == "request_analyzer":
            # リクエスト解析モード：WebViewは使用しないため常に非表示
            if hasattr(self.parent, 'webview'):
                self.parent.webview.setVisible(False)

            if hasattr(self.parent, 'login_control_widget'):
                self.parent.login_control_widget.setVisible(False)

            webview_widget = self.parent.findChild(QWidget, 'webview_widget')
            if webview_widget:
                webview_widget.setVisible(False)

            if hasattr(self.parent, 'overlay_manager'):
                self.parent.overlay_manager.hide_overlay()

            self.setup_request_analyzer_mode()

        # Final safety: overlay must only be visible in data_fetch mode.
        # Async WebView events can fire during/after mode switches.
        if mode != "data_fetch" and hasattr(self.parent, 'overlay_manager'):
            try:
                self._schedule_qt_single_shot(0, self.parent.overlay_manager.hide_overlay, key="hide_overlay_after_mode_switch")
            except Exception:
                pass

        # メッセージラベルの位置を動的に調整
        self.update_message_labels_position(mode)
        # ウィンドウ高さを内容に合わせて詰める（95%ルールを維持するため無効化）
        # QTimer.singleShot(0, self.adjust_window_height_to_contents)

        # --- 既存のダミーメッセージ表示 ---
        if mode == "settings":
            self.show_dummy_message("設定")
        elif mode == "subgroup_create":
            self.show_dummy_message("サブグループ")
        elif mode == "basic_info":
            self.show_dummy_message("基本情報")
        elif mode == "ai_test":
            # AIテストは個別のウィジェットで処理するため、ダミーメッセージは表示しない
            pass
        elif mode == "data_portal":
            # データポータルは個別のウィジェットで処理
            pass

        if PerfMonitor is not None:
            PerfMonitor.end(
                perf_key,
                logger=perf_logger,
                mode=mode,
                elapsed_sec=round(time.perf_counter() - _t0, 6),
            )

    def _refresh_webview_after_show(self):
        """WebViewの背景色と再描画を強制して黒化を緩和する（実行はdata_fetch復帰直後）。"""
        try:
            from qt_compat.widgets import QWidget
            from classes.theme import get_qcolor
            from classes.theme import get_color, ThemeKey

            right_widget = None
            webview_widget = None
            try:
                right_widget = self.parent.findChild(QWidget, 'right_widget')
                webview_widget = self.parent.findChild(QWidget, 'webview_widget')
            except Exception:
                right_widget = None
                webview_widget = None

            if right_widget is not None:
                right_widget.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)}; "
                    f"color: {get_color(ThemeKey.WINDOW_FOREGROUND)};"
                )
            if webview_widget is not None:
                webview_widget.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)}; "
                    f"color: {get_color(ThemeKey.WINDOW_FOREGROUND)};"
                )
            if hasattr(self.parent, 'webview'):
                webview = self.parent.webview
                webview.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};"
                )
                try:
                    page = webview.page() if hasattr(webview, 'page') else None
                    if page is not None and hasattr(page, 'setBackgroundColor'):
                        page.setBackgroundColor(get_qcolor(ThemeKey.WINDOW_BACKGROUND))
                except Exception:
                    pass

                try:
                    webview.updateGeometry()
                    webview.update()
                    webview.repaint()
                except Exception:
                    pass
        except Exception:
            pass
    
    def update_menu_button_styles(self, active_mode):
        """
        メニューボタンのスタイルを更新（フォントサイズ調整付き）
        Args:
            active_mode: アクティブなモード
        """
        for mode, button in self.menu_buttons.items():
            try:
                # ボタンオブジェクトが削除されていないかチェック
                if button is None or not hasattr(button, 'setStyleSheet'):
                    continue
                    
                is_active = (mode == active_mode)

                # 例外（現状維持）: ライト/ダーク切替、ヘルプ、閉じる
                if mode in {"theme", "help", "close"}:
                    button.setStyleSheet(get_menu_button_style(is_active))
                else:
                    button.setStyleSheet(get_grouped_menu_button_style(mode, is_active))
                
                # スタイル変更後にフォントサイズを再調整（安全性チェック付き）
                def safe_adjust_font(b=button):
                    try:
                        if b is not None and hasattr(b, 'isVisible') and b.isVisible():
                            self.adjust_button_font_size(b)
                    except (RuntimeError, AttributeError):
                        # オブジェクトが削除済みまたは属性がない場合は無視
                        pass
                self._schedule_qt_single_shot(50, safe_adjust_font, key=f"adjust_font_{mode}")
            except (RuntimeError, AttributeError):
                # ボタンオブジェクトが削除済みの場合は無視
                continue
    
    def show_dummy_message(self, feature_name):
        """
        未実装機能のダミーメッセージを表示
        Args:
            feature_name: 機能名
        """
        #message = f"【{feature_name}機能】は今後実装予定です。現在はデータ取得機能のみ利用可能です。"
        return
        # 親ウィジェットのメッセージを更新
        if hasattr(self.parent, 'display_manager'):
            self.parent.display_manager.set_message(message)
    
    def get_current_mode(self):
        """
        現在のモードを取得
        Returns:
            str: 現在のモード
        """
        return self.current_mode
       
    def _create_basic_info_ui(self, layout, button_style):
        """
        Step 2.5.2.1: 基本情報UI構築層の分離
        データ取得・Excel・段階実行・ステータス表示の統合UI構築
        """
        from qt_compat.widgets import QApplication, QLabel, QHBoxLayout, QVBoxLayout, QMessageBox, QInputDialog, QSpinBox, QTabWidget, QWidget
        from classes.theme.theme_manager import ThemeManager

        # 右ペインをタブ化（基本情報 / XLSX）
        self.basic_info_tabs = QTabWidget()
        self.basic_info_tabs.setObjectName("basic_info_tabs")
        try:
            from qt_compat.widgets import QSizePolicy

            self.basic_info_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass

        basic_tab = QWidget()
        basic_tab_layout = QVBoxLayout(basic_tab)
        xlsx_tab = QWidget()
        xlsx_tab_layout = QVBoxLayout(xlsx_tab)

        self.basic_info_tabs.addTab(basic_tab, "基本情報")
        self.basic_info_tabs.addTab(xlsx_tab, "XLSX")
        layout.addWidget(self.basic_info_tabs, 1)
        
        try:
            # RDE基本情報取得機能セクション
            data_fetch_label = QLabel("🔄 RDE基本情報取得機能:")
            data_fetch_label.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.TEXT_INFO)}; margin-bottom: 8px; font-size: 12pt;")
            basic_tab_layout.addWidget(data_fetch_label)
            
            # データ取得ボタン用のスタイル（基本情報タブ: 3グループで配色を分離）
            from classes.utils.button_styles import get_button_style
            g1_style = get_button_style('basicinfo_group1')
            g2_style = get_button_style('basicinfo_group2')
            g3_style = get_button_style('basicinfo_group3')

            # 横並びで6ボタンを1行で配置
            btn_layout1 = QHBoxLayout()
            try:
                btn_layout1.setSpacing(6)
            except Exception:
                pass

            # 基本情報取得ボタン（invoice_schema取得も含む）
            self.basic_btn = self.create_auto_resize_button("基本情報取得(ALL)", 155, 36, g1_style)
            basic_btn = self.basic_btn
            basic_btn.setToolTip("全ての基本情報・インボイス情報・invoiceSchema情報を取得します")
            basic_btn.clicked.connect(self.fetch_basic_info)
            btn_layout1.addWidget(basic_btn)

            self.basic_self_btn = self.create_auto_resize_button("基本情報取得(検索)", 170, 36, g1_style)
            basic_self_btn = self.basic_self_btn
            basic_self_btn.setToolTip("検索キーワードに基づく基本情報・インボイス情報・invoiceSchema情報を取得します")
            basic_self_btn.clicked.connect(self.fetch_basic_info_self)
            btn_layout1.addWidget(basic_self_btn)

            # 共通情報のみ取得ボタン
            self.common_only_btn = self.create_auto_resize_button("共通情報のみ取得", 155, 36, g2_style)
            common_only_btn = self.common_only_btn
            common_only_btn.clicked.connect(self.fetch_common_info_only)
            btn_layout1.addWidget(common_only_btn)

            # 共通情報取得2ボタン（取得対象を事前選択）
            self.common_only2_btn = self.create_auto_resize_button("共通情報取得2", 145, 36, g2_style)
            common_only2_btn = self.common_only2_btn
            common_only2_btn.setToolTip("取得対象JSONと取得条件（上書き/古い/無い/スキップ）を選択して共通情報を取得します")
            common_only2_btn.clicked.connect(self.fetch_common_info_only2)
            btn_layout1.addWidget(common_only2_btn)

            # invoice_schema取得ボタン
            self.invoice_schema_btn = self.create_auto_resize_button("invoice_schema取得", 160, 36, g3_style)
            invoice_schema_btn = self.invoice_schema_btn
            invoice_schema_btn.clicked.connect(self.fetch_invoice_schema)
            btn_layout1.addWidget(invoice_schema_btn)

            # サンプル情報取得ボタン（旧: サンプル情報強制取得）
            self.sample_info_btn = self.create_auto_resize_button("サンプル情報取得", 150, 36, g3_style)
            sample_info_btn = self.sample_info_btn
            sample_info_btn.clicked.connect(self.fetch_sample_info_only)
            btn_layout1.addWidget(sample_info_btn)

            btn_layout1.addStretch(1)
            basic_tab_layout.addLayout(btn_layout1)
        except Exception as e:
            self.show_error(f"基本情報画面の1行目ボタン作成でエラーが発生しました: {e}")
            basic_tab_layout.addWidget(QLabel("基本情報機能の一部が利用できません"))

        # 並列ダウンロード数 / 保存フォルダを開く
        try:
            from classes.managers.app_config_manager import get_config_manager

            parallel_row = QHBoxLayout()
            parallel_row.setSpacing(8)

            parallel_label = QLabel("並列ダウンロード数")
            try:
                parallel_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
            except Exception:
                pass

            parallel_spin = QSpinBox(basic_tab)
            parallel_spin.setRange(1, 50)
            parallel_spin.setMinimumWidth(90)

            default_workers = 10
            try:
                cfg = get_config_manager()
                default_workers = int(cfg.get("basic_info.parallel_download_workers", default_workers) or default_workers)
            except Exception:
                default_workers = 10

            parallel_spin.setValue(default_workers)
            parallel_spin.setToolTip("同じエンドポイントへの詳細取得の並列数（既定: 10）")
            self.basic_parallel_download_spinbox = parallel_spin

            def _save_parallel_workers(v: int):
                try:
                    cfg = get_config_manager()
                    cfg.set("basic_info.parallel_download_workers", int(v))
                    cfg.save()
                except Exception:
                    pass

            parallel_spin.valueChanged.connect(_save_parallel_workers)

            from classes.utils.button_styles import get_button_style

            self.open_basic_info_data_dir_btn = self.create_auto_resize_button(
                "📁 保存フォルダを開く",
                180,
                32,
                get_button_style("secondary"),
            )

            def open_basic_info_data_dir():
                import os
                from config.common import ensure_directory_exists, get_dynamic_file_path

                directory = ensure_directory_exists(get_dynamic_file_path("output/rde/data"))
                if not os.path.isdir(directory):
                    QMessageBox.warning(self.parent, "フォルダがありません", f"ディレクトリを作成できませんでした:\n{directory}")
                    return
                try:
                    os.startfile(directory)
                except Exception as e:
                    QMessageBox.warning(self.parent, "フォルダを開けません", f"エクスプローラーで開けませんでした:\n{e}")

            self.open_basic_info_data_dir_btn.clicked.connect(open_basic_info_data_dir)

            parallel_row.addWidget(parallel_label)
            parallel_row.addWidget(parallel_spin)
            parallel_row.addStretch(1)
            parallel_row.addWidget(self.open_basic_info_data_dir_btn)

            basic_tab_layout.addLayout(parallel_row)
        except Exception as e:
            logger.debug("basic_info parallel UI init failed: %s", e)

        # JSON個別取得ボタンは廃止された（v2.1.20）

        try:
            # XLSX関連機能セクション（データ取得機能と区別）
            xlsx_label = QLabel("📊 Excel関連機能:")
            xlsx_label.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.TEXT_WARNING)}; margin-top: 5px; margin-bottom: 3px; font-size: 16pt;")
            xlsx_tab_layout.addWidget(xlsx_label)
            
            # XLSX関連ボタン用のスタイル（橙色系）
            from classes.utils.button_styles import get_button_style
            xlsx_button_style = get_button_style('warning')
            
            # 横並びで3ボタン配置（XLSX関連）
            btn_layout2 = QHBoxLayout()
            
            # XLSX反映ボタン
            apply_basic_info_btn = self.create_auto_resize_button("📄 XLSX反映", 180, 40, xlsx_button_style)
            apply_basic_info_btn.clicked.connect(self.apply_basic_info_to_Xlsx)
            # btn_layout2.addWidget(apply_basic_info_btn)
            
            # まとめXLSXボタン
            self.summary_basic_info_btn = self.create_auto_resize_button("📋 まとめXLSX", 180, 40, xlsx_button_style)
            summary_basic_info_btn = self.summary_basic_info_btn
            summary_basic_info_btn.clicked.connect(self.summary_basic_info_to_Xlsx)
            btn_layout2.addWidget(summary_basic_info_btn)
            
            # まとめXLSXを開くボタン
            self.open_summary_xlsx_btn = self.create_auto_resize_button("📂 まとめXLSXを開く", 200, 40, xlsx_button_style)
            open_summary_xlsx_btn = self.open_summary_xlsx_btn

            def open_summary_xlsx():
                import os

                summary_files = list_summary_workbooks(OUTPUT_DIR, SUMMARY_XLSX_PATH)
                if not summary_files:
                    QMessageBox.warning(self.parent, "ファイルがありません", "出力済みのまとめXLSXが見つかりません。")
                    return

                target_path = summary_files[0]
                if len(summary_files) > 1:
                    items = [path.name for path in summary_files]
                    selection, ok = QInputDialog.getItem(
                        self.parent,
                        "まとめXLSXを選択",
                        "開くファイルを選択してください",
                        items,
                        0,
                        False,
                    )
                    if not ok:
                        return
                    name_to_path = {path.name: path for path in summary_files}
                    target_path = name_to_path.get(selection)
                    if not target_path:
                        QMessageBox.warning(self.parent, "ファイルが見つかりません", "選択したファイルを検出できませんでした。")
                        return

                try:
                    os.startfile(str(target_path))
                except Exception as e:
                    QMessageBox.warning(self.parent, "ファイルを開けません", f"Excelファイルを開けませんでした:\n{e}")

            open_summary_xlsx_btn.clicked.connect(open_summary_xlsx)
            btn_layout2.addWidget(open_summary_xlsx_btn)

            self.open_output_dir_btn = self.create_auto_resize_button("📁 XLSXフォルダを開く", 210, 40, xlsx_button_style)
            open_output_dir_btn = self.open_output_dir_btn

            def open_output_dir():
                import os

                directory = ensure_directory_exists(OUTPUT_DIR)
                if not os.path.isdir(directory):
                    QMessageBox.warning(self.parent, "フォルダがありません", f"ディレクトリを作成できませんでした:\n{directory}")
                    return
                try:
                    os.startfile(directory)
                except Exception as e:
                    QMessageBox.warning(self.parent, "フォルダを開けません", f"エクスプローラーで開けませんでした:\n{e}")

            open_output_dir_btn.clicked.connect(open_output_dir)
            btn_layout2.addWidget(open_output_dir_btn)

            xlsx_tab_layout.addLayout(btn_layout2)
        except Exception as e:
            self.show_error(f"基本情報のXLSX関連ボタン作成でエラーが発生しました: {e}")
            xlsx_tab_layout.addWidget(QLabel("XLSX関連機能が利用できません"))

        try:
            from classes.basic.ui.basic_unified_status_widget import BasicUnifiedStatusWidget
            self.basic_unified_status_widget = BasicUnifiedStatusWidget(self.parent)
            try:
                self.basic_unified_status_widget.set_controller(self)
            except Exception:
                pass
            basic_tab_layout.addWidget(self.basic_unified_status_widget, 1)

            # 基本情報タブバリデータを初期化
            self._initialize_basic_info_tab_validator()
            
        except ImportError as e:
            self.show_error(f"基本情報ステータスウィジェットのインポートに失敗しました: {e}")
            basic_tab_layout.addWidget(QLabel("ステータス表示機能が利用できません"))
        except Exception as e:
            self.show_error(f"基本情報ステータスウィジェットの作成でエラーが発生しました: {e}")
            basic_tab_layout.addWidget(QLabel("ステータス表示機能にエラーが発生しました"))

        # 初回のみ: ウィンドウ幅をディスプレイ幅90%上限で横スクロール不要な幅へ寄せる（可変のまま）
        try:
            top_level = self.parent

            if top_level is not None and not getattr(top_level, "_basic_info_initial_resize_done", False):
                top_level._basic_info_initial_resize_done = True

                def _adjust_width_once():
                    try:
                        table = getattr(self, 'basic_unified_status_widget', None)
                        table = getattr(table, 'table', None)
                        if table is None:
                            return

                        header = table.horizontalHeader()

                        # stretchLastSection=True のままだと「現在の表示幅」に合わせて過小評価されるため、一時的に解除して計測する
                        old_stretch = None
                        try:
                            old_stretch = bool(header.stretchLastSection())
                            header.setStretchLastSection(False)
                        except Exception:
                            old_stretch = None

                        try:
                            table.resizeColumnsToContents()
                        except Exception:
                            pass

                        required_table_width = 0
                        try:
                            required_table_width = int(header.length())
                        except Exception:
                            required_table_width = 0
                            for i in range(table.columnCount()):
                                try:
                                    required_table_width += int(header.sectionSize(i))
                                except Exception:
                                    pass

                        try:
                            if old_stretch is not None:
                                header.setStretchLastSection(bool(old_stretch))
                        except Exception:
                            pass

                        # 現在のviewport幅との差分だけウィンドウを広げる（左メニュー幅などは既にwindow幅に含まれるため差分で十分）
                        viewport_w = 0
                        try:
                            viewport_w = int(table.viewport().width())
                        except Exception:
                            viewport_w = int(table.width()) if hasattr(table, 'width') else 0

                        shortage = max(0, int(required_table_width) - int(viewport_w))

                        # 余白（フレーム/スクロールバー/タブ余白）
                        extra = 80
                        desired = None
                        if hasattr(top_level, 'width'):
                            desired = int(top_level.width()) + int(shortage) + int(extra)
                        else:
                            desired = int(required_table_width) + int(extra)

                        screen = None
                        try:
                            screen = top_level.screen()
                        except Exception:
                            screen = None
                        if screen is None:
                            try:
                                screen = QApplication.primaryScreen()
                            except Exception:
                                screen = None

                        if screen is not None:
                            avail = screen.availableGeometry().width()
                            cap = int(avail * 0.9)
                            desired = min(desired, cap)

                        if hasattr(top_level, 'width') and hasattr(top_level, 'resize'):
                            current_w = int(top_level.width())
                            # shortageが0でも横スクロールが見えている場合があるので、その場合も少し広げる
                            h_scroll_visible = False
                            try:
                                h_scroll_visible = bool(table.horizontalScrollBar().isVisible())
                            except Exception:
                                h_scroll_visible = False

                            if desired > current_w or h_scroll_visible:
                                top_level.resize(max(current_w, desired), int(top_level.height()))
                    except Exception:
                        pass

                # レイアウト確定/列自動調整のタイミング差を吸収するため、数回リトライ
                self._schedule_qt_single_shot(150, _adjust_width_once, key="basic_info_initial_resize_1")
                self._schedule_qt_single_shot(400, _adjust_width_once, key="basic_info_initial_resize_2")
                self._schedule_qt_single_shot(800, _adjust_width_once, key="basic_info_initial_resize_3")
        except Exception:
            pass

        # 入力がある場合はポップアップ表示

        # テーマ再適用関数（ライト/ダーク切替時）
        # NOTE: ThemeManager.theme_changed へのクロージャ接続はテストスイート中に残留しやすい。
        # weakref を使って controller を保持しないようにし、controller がGCされたら自己disconnectする。
        try:
            import weakref

            _rde_self_ref = weakref.ref(self)
        except Exception:
            _rde_self_ref = None

        try:
            _rde_theme_manager = ThemeManager.instance()
        except Exception as e:
            logger.debug("BasicInfo theme manager init failed: %s", e)
            _rde_theme_manager = None

        def _refresh_basic_info_theme(*_args):
            self_obj = None
            try:
                self_obj = _rde_self_ref() if _rde_self_ref is not None else self
            except Exception:
                self_obj = None

            if self_obj is None:
                try:
                    if _rde_theme_manager is not None:
                        _rde_theme_manager.theme_changed.disconnect(_refresh_basic_info_theme)
                except Exception:
                    pass
                return

            try:
                # ボタンスタイル再生成（基本情報タブは3グループ配色）
                from classes.utils.button_styles import get_button_style

                g1_style = get_button_style('basicinfo_group1')
                g2_style = get_button_style('basicinfo_group2')
                g3_style = get_button_style('basicinfo_group3')
                xlsx_button_style_new = f"background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)}; font-weight: bold; border-radius: 4px; border: 1px solid {get_color(ThemeKey.BUTTON_WARNING_BORDER)}; padding: 3px;"

                btn = getattr(self_obj, 'basic_btn', None)
                if btn:
                    btn.setStyleSheet(g1_style)
                btn = getattr(self_obj, 'basic_self_btn', None)
                if btn:
                    btn.setStyleSheet(g1_style)
                btn = getattr(self_obj, 'common_only_btn', None)
                if btn:
                    btn.setStyleSheet(g2_style)
                btn = getattr(self_obj, 'common_only2_btn', None)
                if btn:
                    btn.setStyleSheet(g2_style)
                btn = getattr(self_obj, 'invoice_schema_btn', None)
                if btn:
                    btn.setStyleSheet(g3_style)
                btn = getattr(self_obj, 'sample_info_btn', None)
                if btn:
                    btn.setStyleSheet(g3_style)
                for btn in [
                    getattr(self_obj, 'summary_basic_info_btn', None),
                    getattr(self_obj, 'open_summary_xlsx_btn', None),
                    getattr(self_obj, 'open_output_dir_btn', None),
                ]:
                    if btn:
                        btn.setStyleSheet(xlsx_button_style_new)
                # 統合ステータスのテーマ再適用
                if hasattr(self_obj, 'basic_unified_status_widget') and hasattr(self_obj.basic_unified_status_widget, 'refresh_theme'):
                    self_obj.basic_unified_status_widget.refresh_theme()
            except Exception as e:
                logger.debug("BasicInfo theme refresh failed: %s", e)

        try:
            if _rde_theme_manager is not None:
                _rde_theme_manager.theme_changed.connect(_refresh_basic_info_theme)
        except Exception as e:
            logger.debug("BasicInfo theme signal connect failed: %s", e)
        _refresh_basic_info_theme()
        # メイン画面の検索入力欄は廃止（検索はダイアログ側に集約）

    def _create_widget(self, title, color_key=None):
        """
        ダミー機能用のウィジェットを作成
        Args:
            title: 機能名
            color_key: ThemeKey (任意)。未指定時はタイトルで動的決定
        Returns:
            QWidget: ダミーウィジェット
        """
        from qt_compat.widgets import QLabel, QPushButton
        from classes.theme.theme_keys import ThemeKey
        from classes.theme.theme_manager import get_color
        
        widget = QWidget()
        layout = QVBoxLayout()

        # タイトル→アクセント色マッピング（ThemeKey）
        accent_map = {
            "データ登録": "BUTTON_INFO_BACKGROUND",
            "サブグループ": "BUTTON_SECONDARY_BACKGROUND",
            "基本情報": "BUTTON_API_BACKGROUND",
            "データ取得2": "BUTTON_WEB_BACKGROUND",
            "データポータル": "BUTTON_WARNING_BACKGROUND",
            "ヘルプ": "BUTTON_BLUEGREY_BACKGROUND",
        }
        if isinstance(color_key, str) and color_key.startswith('#'):
            color_key = None
        if color_key is None:
            mapped = accent_map.get(title, "BUTTON_DEFAULT_BACKGROUND")
            color_enum = getattr(ThemeKey, mapped, ThemeKey.BUTTON_DEFAULT_BACKGROUND)
        else:
            color_enum = color_key if isinstance(color_key, ThemeKey) else ThemeKey.BUTTON_DEFAULT_BACKGROUND
        background = get_color(color_enum)
        text_color = get_color(ThemeKey.BUTTON_DEFAULT_TEXT)

        button_style = f"background-color: {background}; color: {text_color}; font-weight: bold; border-radius: 6px;"

        if title == "基本情報":
            self._create_basic_info_ui(layout, button_style)
        elif title == "サブグループ":
            return self._create_subgroup_ui(layout, title, background)
        elif title == "データセット":
            self._create_dataset_ui(layout, widget)
        elif title == "データ登録":
            from classes.data_entry.ui import create_data_register_tab_widget
            register_widget = create_data_register_tab_widget(self, title, button_style)
            # ウィジェット全体をレイアウトに追加（中身を移動しない）
            layout.addWidget(register_widget)
        elif title == "設定":
            self._create_settings_ui(layout, title, button_style)
        elif title == "データ取得2":
            self._create_data_fetch2_ui(layout, widget)
        else:
            self._create_dummy_ui(layout, title, button_style)
        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _create_subgroup_ui(self, layout, title, color):
        """
        Step 2.5.2.2: サブグループUI構築層の分離
        サブグループ作成機能のモジュール化
        """
        from qt_compat.widgets import QLabel
        try:
            from classes.subgroup.ui.subgroup_create_widget import create_subgroup_create_widget
            return create_subgroup_create_widget(self, title, color, self.create_auto_resize_button)
        except ImportError as e:
            self.show_error(f"サブグループ作成モジュールのインポートに失敗しました: {e}")
            layout.addWidget(QLabel("サブグループ作成機能が利用できません"))
        except Exception as e:
            self.show_error(f"サブグループ作成画面の作成でエラーが発生しました: {e}")
            layout.addWidget(QLabel("サブグループ作成機能にエラーが発生しました"))

    def _create_data_fetch2_ui(self, layout, widget):
        """
        Step 2.5.2.5b: データ取得2 UI構築層の分離
        データ取得2機能の高度なUI構築とキャッシュ管理
        """
        # DataFetch2TabWidgetを使ってタブUI化
        try:
            from classes.data_fetch2.ui.data_fetch2_tab_widget import create_data_fetch2_tab_widget
            try:
                from classes.utils.perf_monitor import PerfMonitor
            except Exception:
                PerfMonitor = None

            # bearer_tokenを明示的に渡す
            bearer_token = getattr(self.parent, 'bearer_token', None)

            perf_logger = logging.getLogger("RDE_WebView")
            if PerfMonitor is not None:
                with PerfMonitor.span("data_fetch2:build_tab_widget", logger=perf_logger):
                    self._fetch2_tab_widget = create_data_fetch2_tab_widget(widget, prewarm_filter_widget=True)
            else:
                self._fetch2_tab_widget = create_data_fetch2_tab_widget(widget, prewarm_filter_widget=True)

            # bearer_tokenを個別に設定
            if hasattr(self._fetch2_tab_widget, 'set_bearer_token') and bearer_token:
                self._fetch2_tab_widget.set_bearer_token(bearer_token)

            # get_mode_widget() は末尾に addStretch() を入れるため、
            # ここで伸びるウィジェットにストレッチを与えないと下に大きな余白が残る。
            layout.addWidget(self._fetch2_tab_widget, 1)
        except ImportError as e:
            from qt_compat.widgets import QLabel
            self.show_error(f"データ取得2タブウィジェットのインポートに失敗しました: {e}")
            layout.addWidget(QLabel("データ取得2タブUIが利用できません"))
        except Exception as e:
            from qt_compat.widgets import QLabel
            self.show_error(f"データ取得2タブ画面の作成でエラーが発生しました: {e}")
            layout.addWidget(QLabel("データ取得2タブUIにエラーが発生しました"))

    def _create_dataset_ui(self, layout, widget):
        """
        Step 2.5.2.3: データセットUI構築層の分離  
        データセット開設・修正・データエントリー機能のタブ統合UI構築
        """
        # DatasetTabWidgetを使ってタブUI化
        try:
            from classes.dataset.ui.dataset_tab_widget import create_dataset_tab_widget
            # bearer_tokenを明示的に渡す
            bearer_token = getattr(self.parent, 'bearer_token', None)
            self._dataset_tab_widget = create_dataset_tab_widget(widget, bearer_token=bearer_token, ui_controller=self)
            layout.addWidget(self._dataset_tab_widget)
        except ImportError as e:
            from qt_compat.widgets import QLabel
            self.show_error(f"データセットタブウィジェットのインポートに失敗しました: {e}")
            layout.addWidget(QLabel("データセットタブUIが利用できません"))
        except Exception as e:
            from qt_compat.widgets import QLabel
            self.show_error(f"データセットタブ画面の作成でエラーが発生しました: {e}")
            layout.addWidget(QLabel("データセットタブUIにエラーが発生しました"))

    def _dispose_dataset_open_widget(self):
        """既存のデータセットウィジェットを破棄して次回生成時に再作成させる"""
        existing_widget = getattr(self, 'dataset_open_widget', None)
        if not existing_widget:
            return

        # サブグループ更新通知の登録解除
        try:
            create_tab = getattr(existing_widget, '_dataset_create_tab', None)
            cleanup_cb = getattr(create_tab, '_cleanup_subgroup_callback', None)
            if callable(cleanup_cb):
                cleanup_cb()
        except Exception as cleanup_error:  # pragma: no cover - defensive logging
            logger.debug("データセットウィジェットのクリーンアップに失敗: %s", cleanup_error)

        # レイアウトから切り離して破棄
        try:
            existing_widget.setParent(None)
        except Exception:
            pass
        try:
            existing_widget.deleteLater()
        except Exception:
            pass

        self.dataset_open_widget = None

    def focus_dataset_launch_target(self, target_key: str) -> bool:
        """Switch dataset tab to match the dataset launch target."""

        if target_key in {"data_register", "data_register_batch"}:
            return self._focus_data_register_tab(target_key)

        target_attr_map = {
            "dataset_open": ("open_tab", "_dataset_create_tab"),
            "dataset_edit": ("edit_tab", "_dataset_edit_tab"),
            "dataset_dataentry": ("dataentry_tab", "_dataset_dataentry_tab"),
        }

        attr_pair = target_attr_map.get(target_key)
        if not attr_pair:
            return False

        primary_attr, fallback_attr = attr_pair

        tab_widget = getattr(self, '_dataset_tab_widget', None)
        target_tab = None
        if tab_widget is not None:
            target_tab = getattr(tab_widget, primary_attr, None)

        if target_tab is None:
            dataset_widget = getattr(self, 'dataset_open_widget', None)
            if not dataset_widget:
                return False
            tab_widget = getattr(dataset_widget, '_dataset_tab_widget', None)
            if tab_widget is None:
                return False
            target_tab = getattr(dataset_widget, fallback_attr, None)
        if target_tab is None:
            return False

        try:
            desired_index = tab_widget.indexOf(target_tab)
        except Exception:
            desired_index = -1
        if desired_index < 0:
            return False

        try:
            if tab_widget.currentIndex() != desired_index:
                tab_widget.setCurrentIndex(desired_index)
        except Exception:
            return False
        return True

    def _focus_data_register_tab(self, target_key: str) -> bool:
        """Ensure the data register tab shows the requested sub-tab."""

        if self._apply_data_register_focus(getattr(self, "data_register_widget", None), target_key):
            return True
        parent_widget = getattr(getattr(self, "parent", None), "data_register_tab_widget", None)
        if self._apply_data_register_focus(parent_widget, target_key):
            return True
        return False

    @staticmethod
    def _apply_data_register_focus(widget, target_key: str) -> bool:
        if widget is None:
            return False
        method_name = "focus_batch_register_tab" if target_key == "data_register_batch" else "focus_normal_register_tab"
        focus_method = getattr(widget, method_name, None)
        if callable(focus_method):
            try:
                if focus_method():
                    return True
            except Exception:
                logger.debug("UIController: %s failed", method_name, exc_info=True)
        tab_widget = getattr(widget, "tab_widget", None)
        if tab_widget is not None:
            try:
                if tab_widget.count() > 0:
                    if target_key == "data_register_batch":
                        target_index = getattr(widget, "_batch_tab_index", 1) or 1
                    else:
                        target_index = getattr(widget, "_normal_tab_index", 0) or 0
                    target_index = max(0, min(target_index, tab_widget.count() - 1))
                    tab_widget.setCurrentIndex(target_index)
                    return True
            except Exception:
                logger.debug("UIController: direct data register tab focus failed", exc_info=True)
        return False

    def _create_dummy_ui(self, layout, title, button_style):
        """
        Step 2.5.2.5c: ダミーUI構築層の分離
        未実装機能用の汎用ダミーUI構築
        """
        button_text = f"{title}実行（ダミー）"
        button = self.create_auto_resize_button(
            button_text, 200, 40, button_style
        )
        button.clicked.connect(lambda: self.show_dummy_message(title))
        layout.addWidget(button)

    def get_mode_widget(self, mode):
        """
        指定されたモードのウィジェットを取得
        Args:
            mode: モード名
        Returns:
            QWidget: モードウィジェット
        """
        if mode == "data_fetch":
            from qt_compat.widgets import QWidget, QVBoxLayout
            if self.data_fetch_widget is None:
                self.data_fetch_widget = QWidget()
                self.data_fetch_layout = QVBoxLayout()
                
                # 画像取得上限設定を追加
                limit_layout = self.create_image_limit_dropdown()
                if limit_layout:
                    self.data_fetch_layout.addLayout(limit_layout)
                
                self.data_fetch_widget.setLayout(self.data_fetch_layout)
            return self.data_fetch_widget
        elif mode == "dataset_open":
            try:
                if self.dataset_open_widget is None:
                    from classes.dataset.ui.dataset_open_widget import create_dataset_open_widget
                    self.dataset_open_widget = create_dataset_open_widget(
                        parent=self.parent,
                        title="データセット",
                        create_auto_resize_button=self.create_auto_resize_button
                    )
                return self.dataset_open_widget
            except Exception as e:
                import traceback
                log_path = None
                try:
                    from config.common import DEBUG_LOG_PATH
                    log_path = DEBUG_LOG_PATH
                except Exception:
                    log_path = "debug_trace.log"
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"[ERROR] dataset_open_widget: {e}\n{traceback.format_exc()}\n")
                from qt_compat.widgets import QMessageBox, QWidget
                QMessageBox.critical(None, "データセット開設エラー", f"データセット開設ページの生成に失敗しました。\n{e}")
                return QWidget()
        elif mode == "data_register":
            if self.data_register_widget is None:
                try:
                    logger.debug("データ登録タブウィジェット作成開始")
                    from classes.data_entry.ui.data_register_tab_widget import create_data_register_tab_widget
                    self.data_register_widget = create_data_register_tab_widget(self, "データ登録")
                    logger.debug("データ登録タブウィジェット作成結果: %s", type(self.data_register_widget))
                    if self.data_register_widget is None:
                        logger.debug("データ登録タブウィジェット作成失敗 - フォールバック使用")
                        # フォールバック：従来のダミーウィジェット
                        self.data_register_widget = self._create_widget("データ登録")
                    else:
                        logger.debug("データ登録タブウィジェット作成成功")
                        
                        # 初回のデータ登録ウィジェット作成時に95%の高さを適用
                        self._apply_initial_data_register_sizing()
                        
                except Exception as e:
                    logger.error("データ登録ウィジェット作成エラー: %s", e)
                    import traceback
                    traceback.print_exc()
                    self.data_register_widget = self._create_widget("データ登録")
            return self.data_register_widget
        elif mode == "sample_dedup":
            if not hasattr(self, "sample_dedup_widget") or self.sample_dedup_widget is None:
                try:
                    from classes.subgroup.ui.sample_dedup_tab_widget import create_sample_dedup_tab_widget
                    self.sample_dedup_widget = create_sample_dedup_tab_widget(self.parent)
                except Exception as e:
                    logger.error("試料ウィジェット作成エラー: %s", e)
                    self.sample_dedup_widget = self._create_widget("試料")
            return self.sample_dedup_widget
        elif mode == "request_analyzer":
            return self._create_request_analyzer_widget()
        elif mode == "settings":
            if self.settings_widget is None:
                try:
                    from classes.config.ui.settings_tab_widget import create_settings_tab_widget
                    self.settings_widget = create_settings_tab_widget(self.parent, getattr(self.parent, 'bearer_token', None))
                    if self.settings_widget is None:
                        # フォールバック：従来の設定ダイアログを開くボタン
                        self.settings_widget = self._create_fallback_settings_widget()
                except Exception as e:
                    logger.error("設定ウィジェット作成エラー: %s", e)
                    self.settings_widget = self._create_fallback_settings_widget()
            return self.settings_widget
        elif mode == "subgroup_create":
            return self._create_widget("サブグループ")
        elif mode == "basic_info":
            return self._create_widget("基本情報")
        elif mode == "data_fetch2":
            return self._create_widget("データ取得2")
        elif mode == "ai_test":
            return self._create_ai_test_widget()
        elif mode == "data_portal":
            if self.data_portal_widget is None:
                try:
                    from classes.data_portal.ui.data_portal_widget import DataPortalWidget
                    self.data_portal_widget = DataPortalWidget(self.parent)
                except Exception as e:
                    logger.error("データポータルウィジェット作成エラー: %s", e)
                    import traceback
                    traceback.print_exc()
                    self.data_portal_widget = self._create_widget("データポータル")
            return self.data_portal_widget
        elif mode == "help":
            if not hasattr(self, 'help_widget') or self.help_widget is None:
                try:
                    from classes.help.ui.help_widget import create_help_widget
                    self.help_widget = create_help_widget(self.parent)
                    if self.help_widget is None:
                        # フォールバック：エラーメッセージ
                        self.help_widget = self._create_widget("ヘルプ")
                except Exception as e:
                    logger.error("ヘルプウィジェット作成エラー: %s", e)
                    self.help_widget = self._create_widget("ヘルプ")
            return self.help_widget
        else:
            return None
        return None
    
    def setup_request_analyzer_mode(self):
        """
        リクエスト解析モードのセットアップ
        WebViewのログイン状態とCookieセッションを活用
        オーバーレイを解除してWebView操作を可能にする
        """
        try:
            # RDEリクエスト解析GUIを認証付きで起動
            from tools.rde_dataset_creation_gui import create_authenticated_gui
            
            # 親ウィジェットからWebViewとCookie情報を取得
            webview = None
            
            if hasattr(self.parent, 'webview'):
                webview = self.parent.webview
                """
                # WebViewからCookieを取得
                try:
                    from qt_compat.webengine import QWebEngineProfile
                    profile = webview.page().profile()
                    cookie_store = profile.cookieStore()
                    
                    # 現在のページのURLを取得
                    current_url = webview.url().toString() if webview.url() else ""
                    
                    # オーバーレイマネージャーを取得してオーバーレイを解除
                    if hasattr(self.parent, 'overlay_manager'):
                        self.parent.overlay_manager.hide_overlay()
                        self.overlay_disabled_for_analyzer = True
                        logger.debug("解析ツール用にオーバーレイを無効化しました")
                        
                        # WebViewのナビゲーション変更でオーバーレイが再表示されないように監視
                        self.setup_overlay_prevention()
                    
                    # WebViewを明示的に有効化
                    webview.setEnabled(True)
                    webview.setAttribute(webview.WA_TransparentForMouseEvents, False)
                    webview.setFocusPolicy(webview.StrongFocus)
                    webview.show()
                    webview.raise_()
                    
                    # WebViewの状態をデバッグ表示
                    logger.debug("WebView状態確認:")
                    logger.debug("  - isEnabled: %s", webview.isEnabled())
                    logger.debug("  - isVisible: %s", webview.isVisible())
                    logger.debug("  - focusPolicy: %s", webview.focusPolicy())
                    logger.debug("  - hasMouseTracking: %s", webview.hasMouseTracking())
                    logger.debug("WebViewを操作可能状態に設定しました")
                    
                    if hasattr(self.parent, 'display_manager'):
        # データセット開設ボタン生成は_create_widgetで処理されるため、ここでは不要
                    
                except Exception as e:
                    logger.error("WebView情報取得エラー: %s", e)
                """
            # 認証付きリクエスト解析GUIを起動（WebView情報を渡す）
            self.analyzer_gui = create_authenticated_gui(parent_webview=webview, parent_controller=self)
            
            if self.analyzer_gui:
                # 認証成功時のみ処理を続行
                # 現在のモードを更新
                self.current_mode = "request_analyzer"
                
                # WebViewのナビゲーション変更を監視
                self.setup_webview_monitoring()
                
                # メッセージ表示
                if hasattr(self.parent, 'display_manager'):
                    self.parent.display_manager.set_message("リクエスト解析ツール起動完了 - WebView内のリンククリックが可能です")
                
                logger.debug("リクエスト解析ツールがWebView連携で起動されました")
            else:
                # 認証失敗時の処理
                if hasattr(self.parent, 'display_manager'):
                    self.parent.display_manager.set_message("リクエスト解析ツール: 認証に失敗しました")
                
                # オーバーレイを元に戻す
                if hasattr(self.parent, 'overlay_manager') and self.overlay_disabled_for_analyzer:
                    self.parent.overlay_manager.show_overlay()
                    self.overlay_disabled_for_analyzer = False
                    logger.debug("認証失敗のためオーバーレイを復元しました")
                
                logger.debug("リクエスト解析ツール: 認証に失敗しました")
                
        except ImportError as e:
            error_msg = f"リクエスト解析ツールのインポートエラー: {e}"
            print(error_msg)
            if hasattr(self.parent, 'display_manager'):
                self.parent.display_manager.set_message(error_msg)
        except Exception as e:
            error_msg = f"リクエスト解析ツール起動エラー: {e}"
            print(error_msg)
            if hasattr(self.parent, 'display_manager'):
                self.parent.display_manager.set_message(error_msg)
    
    def setup_overlay_prevention(self):
        """解析ツールモード中のオーバーレイ再表示を防止"""
        try:
            # WebViewのナビゲーション完了時にオーバーレイを強制非表示
            if hasattr(self.parent, 'webview'):
                webview = self.parent.webview
                
                # 既存のloadFinishedシグナルに追加で接続（強制オーバーレイ制御）
                if not self._request_analyzer_overlay_prevention_connected:
                    webview.page().loadFinished.connect(self.prevent_overlay_on_navigation)
                    self._request_analyzer_overlay_prevention_connected = True
                logger.debug("オーバーレイ防止監視を開始しました")
                
        except Exception as e:
            logger.error("オーバーレイ防止設定エラー: %s", e)
    
    def prevent_overlay_on_navigation(self, ok):
        """ナビゲーション時のオーバーレイ再表示を防止"""
        try:
            if self.overlay_disabled_for_analyzer and hasattr(self.parent, 'overlay_manager'):
                # 解析ツールモード中は常にオーバーレイを非表示に保つ
                self.parent.overlay_manager.hide_overlay()
                
                # WebViewも再度有効化
                if hasattr(self.parent, 'webview'):
                    webview = self.parent.webview
                    webview.setEnabled(True)
                    webview.setAttribute(webview.WA_TransparentForMouseEvents, False)
                    webview.setFocusPolicy(webview.StrongFocus)
                
                logger.debug("ナビゲーション後: オーバーレイを再度無効化しました")
                
        except Exception as e:
            logger.error("オーバーレイ防止処理エラー: %s", e)

    def setup_webview_monitoring(self):
        """WebViewのナビゲーション変更を監視してリクエストを自動解析"""
        
        if hasattr(self.parent, 'webview') and self.analyzer_gui:
            webview = self.parent.webview

            if self._request_analyzer_webview_monitoring_connected:
                return
            
            # URLが変更された時のシグナルを接続
            try:
                webview.urlChanged.connect(self.on_webview_url_changed)
                webview.loadStarted.connect(self.on_webview_load_started)
                webview.page().loadFinished.connect(self.on_webview_load_finished)
                self._request_analyzer_webview_monitoring_connected = True
                logger.debug("WebView監視を開始しました")
            except Exception as e:
                logger.error("WebView監視設定エラー: %s", e)
    
    def on_webview_url_changed(self, url):
        """WebViewのURL変更時の処理"""
        if self.analyzer_gui and hasattr(self.analyzer_gui, 'log_webview_navigation'):
            url_str = url.toString()
            self.analyzer_gui.log_webview_navigation(url_str, "URL変更")
            if hasattr(self.parent, 'display_manager'):
                self.parent.display_manager.set_message(f"WebView遷移検出: {url_str[:60]}...")
    
    def on_webview_load_started(self):
        """WebViewのロード開始時の処理"""
        if self.analyzer_gui and hasattr(self.analyzer_gui, 'log_webview_navigation'):
            if hasattr(self.parent, 'webview'):
                current_url = self.parent.webview.url().toString()
                self.analyzer_gui.log_webview_navigation(current_url, "ロード開始")

        # 遷移中にWebViewが黒くクリアされる環境があるため、
        # loadStartedのタイミングでも背景色を明示しておく。
        try:
            from qt_compat.widgets import QWidget
            from classes.theme import get_qcolor
            from classes.theme import get_color, ThemeKey

            right_widget = None
            webview_widget = None
            try:
                right_widget = self.parent.findChild(QWidget, 'right_widget')
                webview_widget = self.parent.findChild(QWidget, 'webview_widget')
            except Exception:
                right_widget = None
                webview_widget = None

            if right_widget is not None:
                right_widget.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)}; "
                    f"color: {get_color(ThemeKey.WINDOW_FOREGROUND)};"
                )
            if webview_widget is not None:
                webview_widget.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)}; "
                    f"color: {get_color(ThemeKey.WINDOW_FOREGROUND)};"
                )
            if hasattr(self.parent, 'webview'):
                self.parent.webview.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};"
                )
                try:
                    page = self.parent.webview.page() if hasattr(self.parent.webview, 'page') else None
                    if page is not None and hasattr(page, 'setBackgroundColor'):
                        page.setBackgroundColor(get_qcolor(ThemeKey.WINDOW_BACKGROUND))
                except Exception:
                    pass
        except Exception:
            pass
    
    def on_webview_load_finished(self, ok):
        """WebViewのロード完了時の処理（オーバーレイ防止強化）"""
        if self.analyzer_gui and hasattr(self.analyzer_gui, 'log_webview_navigation'):
            if hasattr(self.parent, 'webview'):
                current_url = self.parent.webview.url().toString()
                status = "ロード完了" if ok else "ロード失敗"
                self.analyzer_gui.log_webview_navigation(current_url, status)
                if hasattr(self.parent, 'display_manager'):
                    self.parent.display_manager.set_message(f"WebView {status}: {current_url[:60]}...")
        
        # 解析ツールモード中は常にオーバーレイを無効化
        if self.overlay_disabled_for_analyzer:
            self.force_disable_overlay_after_navigation()
    
    def force_disable_overlay_after_navigation(self):
        """ナビゲーション後の強制オーバーレイ無効化"""
        try:
            # オーバーレイマネージャーを強制無効化
            if hasattr(self.parent, 'overlay_manager'):
                self.parent.overlay_manager.hide_overlay()
                
            # WebViewを再度操作可能状態に設定
            if hasattr(self.parent, 'webview'):
                webview = self.parent.webview
                webview.setEnabled(True)
                webview.setAttribute(webview.WA_TransparentForMouseEvents, False)
                webview.setFocusPolicy(webview.StrongFocus)
                webview.show()
                webview.raise_()
                
            # 少し遅延してもう一度実行（確実に無効化）
            self._schedule_qt_single_shot(500, self.delayed_overlay_disable, key="delayed_overlay_disable")
            
            logger.debug("ナビゲーション後: オーバーレイを強制無効化しました")
            
        except Exception as e:
            logger.error("オーバーレイ強制無効化エラー: %s", e)
    
    def delayed_overlay_disable(self):
        """遅延オーバーレイ無効化"""
        try:
            if self.overlay_disabled_for_analyzer and hasattr(self.parent, 'overlay_manager'):
                self.parent.overlay_manager.hide_overlay()
                logger.debug("遅延オーバーレイ無効化実行")
        except Exception as e:
            logger.error("遅延オーバーレイ無効化エラー: %s", e)
    
    def cleanup_request_analyzer_mode(self):
        """リクエスト解析モード終了時のクリーンアップ"""
        try:
            # WebView監視を停止
            if hasattr(self.parent, 'webview'):
                webview = self.parent.webview
                if self._request_analyzer_webview_monitoring_connected:
                    try:
                        webview.urlChanged.disconnect(self.on_webview_url_changed)
                    except Exception:
                        pass
                    try:
                        webview.loadStarted.disconnect(self.on_webview_load_started)
                    except Exception:
                        pass
                    try:
                        webview.page().loadFinished.disconnect(self.on_webview_load_finished)
                    except Exception:
                        pass
                    self._request_analyzer_webview_monitoring_connected = False

                # overlay prevention (optional)
                if self._request_analyzer_overlay_prevention_connected:
                    try:
                        webview.page().loadFinished.disconnect(self.prevent_overlay_on_navigation)
                    except Exception:
                        pass
                    self._request_analyzer_overlay_prevention_connected = False
            
            # 解析ツールGUIを閉じる
            if self.analyzer_gui:
                try:
                    self.analyzer_gui.close()
                    self.analyzer_gui = None
                except:
                    pass
            
            # オーバーレイを復元（解析ツール専用で無効化していた場合）
            if self.overlay_disabled_for_analyzer and hasattr(self.parent, 'overlay_manager'):
                # 現在のモードに応じてオーバーレイを復元
                if self.current_mode != "request_analyzer":
                    self.parent.overlay_manager.show_overlay()
                    if hasattr(self.parent, 'display_manager'):
                        self.parent.display_manager.set_message("WebView操作制限を復元しました")
                
                self.overlay_disabled_for_analyzer = False
            
            # 現在のモードをリセット
            if self.current_mode == "request_analyzer":
                self.current_mode = "data_fetch"  # デフォルトモードに戻す
            
            logger.info("リクエスト解析モードのクリーンアップ完了")
            
        except Exception as e:
            logger.error("クリーンアップエラー: %s", e)
    
    def _create_request_analyzer_widget(self):
        """リクエスト解析モード用のウィジェットを作成"""
        from qt_compat.widgets import QLabel, QPushButton, QTextEdit
        
        widget = QWidget()
        layout = QVBoxLayout()
        
        # タイトル
        title = QLabel("RDE HTTPリクエスト解析ツール")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)}; padding: 10px;")
        layout.addWidget(title)
        
        # 説明
        desc = QLabel("データセット開設機能調査用のHTTPリクエスト・レスポンス解析ツール\n"
                     "メインアプリのWebViewログイン状態とCookieセッションを活用します")
        desc.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SECONDARY)}; padding: 5px 10px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # 起動ボタン
        button = self.create_auto_resize_button(
            "リクエスト解析GUI起動", 200, 40, 
            f"background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)}; font-weight: bold; border-radius: 6px;"
        )
        button.clicked.connect(self.setup_request_analyzer_mode)
        layout.addWidget(button)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def _initialize_basic_info_tab_validator(self):
        """基本情報タブバリデータの初期化"""
        try:
            from classes.basic.ui.tab_validator import create_basic_info_tab_validator
            self.basic_info_tab_validator = create_basic_info_tab_validator(self.parent, self)
            logger.info("基本情報タブバリデータを初期化しました")
        except Exception as e:
            logger.error(f"基本情報タブバリデータの初期化エラー: {e}")
    
    def _initialize_task_data(self):
        """タスクデータの初期化（遅延実行用）"""
        try:
            logger.debug("_initialize_task_data called")
            
            # ウィジェットの存在確認
            if not hasattr(self, 'task_id_combo'):
                logger.error("task_id_combo is not initialized")
                return
                
            if not hasattr(self, 'experiment_combo'):
                logger.error("experiment_combo is not initialized")
                return
                
            logger.debug("task_id_combo initialized: %s", self.task_id_combo is not None)
            logger.debug("experiment_combo initialized: %s", self.experiment_combo is not None)
            
            # データソースの初期選択を確認
            if hasattr(self, 'arim_exp_radio') and hasattr(self, 'normal_exp_radio'):
                logger.debug("arim_exp_radio checked: %s", self.arim_exp_radio.isChecked())
                logger.debug("normal_exp_radio checked: %s", self.normal_exp_radio.isChecked())
                
                # どちらも選択されていない場合は、標準実験データを選択
                if not self.arim_exp_radio.isChecked() and not self.normal_exp_radio.isChecked():
                    logger.debug("No datasource selected, defaulting to normal_exp_radio")
                    self.normal_exp_radio.setChecked(True)
            
            # 課題番号リストを更新
            self.refresh_task_ids()
            
        except Exception as e:
            logger.error("_initialize_task_data failed: %s", e)
            import traceback
            traceback.print_exc()
    
    def _init_ai_settings(self):
        """AI設定の初期化"""
        try:
            from classes.ai.core.ai_manager import AIManager
            self.ai_manager = AIManager()
            
            # UIコンポーネントが存在する場合のみ更新
            if hasattr(self, 'ai_provider_combo') and self.ai_provider_combo:
                # プロバイダー一覧を更新
                self.ai_provider_combo.clear()
                providers = self.ai_manager.get_available_providers()
                if not providers:
                    self.ai_provider_combo.addItem("設定なし")
                    if hasattr(self, 'ai_model_combo') and self.ai_model_combo:
                        self.ai_model_combo.clear()
                        self.ai_model_combo.addItem("設定なし")
                else:
                    self.ai_provider_combo.addItems(providers)
                    self.ai_provider_combo.currentTextChanged.connect(self._update_model_list)
                    
                    # デフォルトプロバイダーを設定
                    default_provider = self.ai_manager.get_default_provider()
                    if default_provider in providers:
                        self.ai_provider_combo.setCurrentText(default_provider)
                        self._update_model_list(default_provider)
                    else:
                        self._update_model_list(providers[0] if providers else "")
            
            # データソースの初期化（UIコンポーネント無しでも実行可能）
            if hasattr(self, '_init_datasource_selection'):
                self._init_datasource_selection()
                
        except Exception as e:
            # 安全なログ出力（複数フォールバック）
            error_msg = f"AI設定の初期化に失敗: {e}"
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(error_msg)
            elif hasattr(self, 'force_log'):
                self.force_log(error_msg, "ERROR")
            else:
                logger.error("%s", error_msg)
    
    def _update_model_list(self, provider):
        """選択されたプロバイダーのモデル一覧を更新"""
        try:
            # UIコンポーネントが存在する場合のみ更新
            if hasattr(self, 'ai_model_combo') and self.ai_model_combo:
                self.ai_model_combo.clear()
                if provider and provider != "設定なし":
                    models = self.ai_manager.get_models_for_provider(provider)
                    if models:
                        self.ai_model_combo.addItems(models)
                        # デフォルトモデルを選択
                        default_model = self.ai_manager.get_default_model(provider)
                        if default_model and default_model in models:
                            self.ai_model_combo.setCurrentText(default_model)
                    else:
                        self.ai_model_combo.addItem("モデルなし")
                else:
                    self.ai_model_combo.addItem("設定なし")
        except Exception as e:
            # 安全なログ出力（複数フォールバック）
            error_msg = f"モデル一覧の更新に失敗: {e}"
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(error_msg)
            elif hasattr(self, 'force_log'):
                self.force_log(error_msg, "ERROR")
            else:
                logger.error("%s", error_msg)
    
    def _init_datasource_selection(self):
        """データソース選択の初期化"""
        try:
            import os
            
            # ファイルの存在確認
            arim_exp_exists = os.path.exists(os.path.join(INPUT_DIR, "ai", "arim_exp.xlsx"))
            normal_exp_exists = os.path.exists(os.path.join(INPUT_DIR, "ai", "exp.xlsx"))
            
            if not hasattr(self, 'arim_exp_radio') or not hasattr(self, 'normal_exp_radio'):
                logger.debug("データソースラジオボタンが初期化されていません")
                return
            
            if arim_exp_exists and normal_exp_exists:
                # 両方存在する場合はarim_exp.xlsxをデフォルトに
                self.arim_exp_radio.setEnabled(True)
                self.normal_exp_radio.setEnabled(True)
                self.arim_exp_radio.setChecked(True)
                self.datasource_info_label.setText("📊 両方のデータファイルが利用可能です。ARIM実験データがデフォルトで選択されています。")
                logger.debug("両方のファイルが存在 - ARIM実験データを選択")
            elif arim_exp_exists:
                # arim_exp.xlsxのみ存在
                self.arim_exp_radio.setEnabled(True)
                self.normal_exp_radio.setEnabled(False)
                self.arim_exp_radio.setChecked(True)
                self.datasource_info_label.setText("📊 ARIM実験データのみ利用可能です。")
                logger.debug("ARIM実験データのみ存在")
            elif normal_exp_exists:
                # exp.xlsxのみ存在
                self.arim_exp_radio.setEnabled(False)
                self.normal_exp_radio.setEnabled(True)
                self.normal_exp_radio.setChecked(True)
                self.datasource_info_label.setText("📊 標準実験データのみ利用可能です。")
                logger.debug("標準実験データのみ存在")
            else:
                # どちらも存在しない
                self.arim_exp_radio.setEnabled(False)
                self.normal_exp_radio.setEnabled(False)
                self.datasource_info_label.setText("⚠️ 実験データファイルが見つかりません。")
                logger.debug("実験データファイルが存在しません")
                
        except Exception as e:
            logger.error("データソース初期化エラー: %s", e)
            if hasattr(self, 'datasource_info_label'):
                self.datasource_info_label.setText(f"⚠️ データソース初期化エラー: {e}")
    
    def on_datasource_changed(self, button):
        """データソース変更時の処理"""
        try:
            if button == self.arim_exp_radio and button.isChecked():
                logger.debug("ARIM実験データが選択されました")
                self.datasource_info_label.setText("📊 ARIM実験データ (arim_exp.xlsx) を使用します。詳細な課題情報と実験手法が含まれます。")
            elif button == self.normal_exp_radio and button.isChecked():
                logger.debug("標準実験データが選択されました")
                self.datasource_info_label.setText("📊 標準実験データ (exp.xlsx) を使用します。基本的な実験情報が含まれます。")
            
            # 課題番号リストを更新
            self.refresh_task_ids()
            
        except Exception as e:
            logger.error("データソース変更処理エラー: %s", e)
            if hasattr(self, 'datasource_info_label'):
                self.datasource_info_label.setText(f"⚠️ データソース変更エラー: {e}")
    
    def show_progress(self, message="処理中...", current=0, total=100):
        """プログレス表示を開始（経過時間記録開始）"""
        import time
        
        logger.debug("show_progress called: message='%s', current=%s, total=%s", message, current, total)
        
        # 開始時刻を記録
        self._progress_start_time = time.time()
        
        if hasattr(self, 'ai_progress_bar') and hasattr(self, 'ai_progress_label'):
            logger.debug("Progress elements found - showing progress")
            self.ai_progress_bar.setVisible(True)
            self.ai_progress_label.setVisible(True)
            self.ai_progress_bar.setValue(current)
            self.ai_progress_bar.setMaximum(total)
            
            # 経過時間付きメッセージ
            elapsed_text = self._format_elapsed_time(0)
            full_message = f"{message} [{elapsed_text}]"
            self.ai_progress_label.setText(full_message)
            logger.debug("Progress label set to: '%s'", full_message)
            
            # UIを強制更新
            from qt_compat.widgets import QApplication
            QApplication.processEvents()
        else:
            logger.debug("Progress elements not found:")
            logger.debug("ai_progress_bar exists: %s", hasattr(self, 'ai_progress_bar'))
            logger.debug("ai_progress_label exists: %s", hasattr(self, 'ai_progress_label'))
    
    def update_progress(self, current, total, message=None):
        """プログレス更新（経過時間表示付き）"""
        logger.debug("update_progress called: current=%s, total=%s, message='%s'", current, total, message)
        
        if hasattr(self, 'ai_progress_bar') and hasattr(self, 'ai_progress_label'):
            self.ai_progress_bar.setValue(current)
            self.ai_progress_bar.setMaximum(total)
            
            if message:
                # 経過時間を計算して表示
                elapsed_seconds = 0
                if hasattr(self, '_progress_start_time'):
                    import time
                    elapsed_seconds = time.time() - self._progress_start_time
                
                elapsed_text = self._format_elapsed_time(elapsed_seconds)
                progress_percent = int((current / total * 100)) if total > 0 else 0
                full_message = f"{message} [{elapsed_text}] ({progress_percent}%)"
                self.ai_progress_label.setText(full_message)
                logger.debug("Progress updated: '%s'", full_message)
            
            # UIを強制更新
            from qt_compat.widgets import QApplication
            QApplication.processEvents()
        else:
            logger.debug("Progress elements not found in update_progress")
    
    def _format_elapsed_time(self, seconds):
        """経過時間を見やすい形式でフォーマット"""
        if seconds < 1:
            return "0秒"
        elif seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}分{secs}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}時間{minutes}分"
    
    def hide_progress(self):
        """プログレス表示を非表示（最終経過時間表示）"""
        logger.debug("hide_progress called")
        
        if hasattr(self, 'ai_progress_bar') and hasattr(self, 'ai_progress_label'):
            # 最終経過時間を計算
            final_elapsed = 0
            if hasattr(self, '_progress_start_time'):
                import time
                final_elapsed = time.time() - self._progress_start_time
            
            # 最終時間をログに出力
            if final_elapsed > 0:
                elapsed_text = self._format_elapsed_time(final_elapsed)
                logger.debug("Final elapsed time: %s", elapsed_text)
                # ai_response_displayの存在と有効性を確認
                if (hasattr(self, 'ai_response_display') and 
                    self.ai_response_display is not None):
                    try:
                        self.ai_response_display.append(f"[INFO] 処理完了 - 総経過時間: {elapsed_text}")
                    except RuntimeError:
                        logger.warning("ai_response_display が削除されているため、最終時間表示をスキップ")
            
            self.ai_progress_bar.setVisible(False)
            self.ai_progress_label.setVisible(False)
            logger.debug("Progress elements hidden")
        else:
            logger.debug("Progress elements not found in hide_progress")
            
            # 開始時刻をリセット
            if hasattr(self, '_progress_start_time'):
                delattr(self, '_progress_start_time')
    
    # ===== 動的メソッド委譲システム =====
    def __getattr__(self, name):
        """存在しないメソッドの動的委譲処理"""
        # AIコントローラーへの委譲
        ai_methods = [
            'test_ai_connection', 'send_ai_prompt', 'execute_ai_analysis',
            # AI分析関連メソッド
            'analyze_material_index', 'analyze_material_index_single',
            '_load_arim_extension_data', '_merge_with_arim_data',
            '_load_experiment_data', '_load_material_index', 
            '_load_prompt_template', '_build_analysis_prompt',
            'prepare_exp_info', 'prepare_exp_info_ext', 
            'prepare_device_info', 'prepare_quality_metrics'
        ]
        if name in ai_methods and hasattr(self, 'ai_controller'):
            return getattr(self.ai_controller, name)
        
        # データコントローラーへの委譲
        data_methods = [
            'setup_data_fetch_mode', 'fetch_basic_info', 'fetch_basic_info_self',
            'summary_basic_info_to_Xlsx', 'apply_basic_info_to_Xlsx', 
            'fetch_common_info_only', 'fetch_invoice_schema', 'fetch_sample_info_only',
            'open_file_selector', 'register_selected_datasets', 'validate_datasets'
        ]
        if name in data_methods and hasattr(self, 'data_controller'):
            return getattr(self.data_controller, name)
        
        # フォームコントローラーへの委譲
        forms_methods = [
            'create_expand_button', 'update_sample_form', 'validate_sample_info_early',
            'set_sample_inputs_enabled', 'create_image_limit_dropdown'
        ]
        if name in forms_methods and hasattr(self, 'forms_controller'):
            return getattr(self.forms_controller, name)
        
        # 該当なしの場合はAttributeErrorを発生
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def show_dataset_info(self, dataset_id):
        """データセット情報表示（データコントローラーに委譲）"""
        return self.data_controller.show_dataset_info(dataset_id)

    def _load_arim_extension_data(self):
        """ARIM拡張情報（converted.xlsx）を読み込む - UI Controller AIに委譲"""
        result = self.ai_controller._load_arim_extension_data()
        # current_arim_dataの設定を維持
        self.current_arim_data = result
        return result
    
    def _merge_with_arim_data(self, experiment_data, arim_data):
        """
        実験データとARIM拡張データをARIMNOで結合（UIControllerAIに委譲）
        
        【重要】ARIM拡張情報統合の委譲ポイント
        このメソッドはUIControllerAIの_merge_with_arim_dataメソッドに処理を委譲します。
        ARIM拡張データの統合はAI機能の重要な一部であり、プロンプト生成時に
        ARIM拡張情報が欠落しないよう注意が必要です。
        
        【コメント追加理由】
        - 過去にARIM拡張情報がプロンプトから欠落する問題が発生
        - この委譲ポイントでエラーが発生するとARIM拡張データが失われる
        - AIController の可用性確認が重要
        """
        try:
            # UIControllerAIの対応メソッドに委譲
            if hasattr(self, 'ai_controller') and self.ai_controller:
                return self.ai_controller._merge_with_arim_data(experiment_data, arim_data)
            else:
                logger.error("AIコントローラーが利用できません")
                return experiment_data
        except Exception as e:
            logger.error("ARIMデータ結合委譲エラー: %s", e)
            return experiment_data
    
    def _load_experiment_data(self):
        """実験データを読み込み（選択されたデータソースに応じて）"""
        try:
            import pandas as pd
            import os
            
            # データソース選択を確認
            use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                           self.arim_exp_radio.isChecked() and 
                           self.arim_exp_radio.isEnabled())
            
            if use_arim_data:
                exp_file_path = os.path.join(INPUT_DIR, "ai", "arim_exp.xlsx")
                data_source_name = "ARIM実験データ"
            else:
                exp_file_path = os.path.join(INPUT_DIR, "ai", "exp.xlsx")
                data_source_name = "標準実験データ"
            
            logger.debug("%sを読み込み中: %s", data_source_name, exp_file_path)
            
            if not os.path.exists(exp_file_path):
                self.ai_response_display.append(f"[ERROR] {data_source_name}ファイルが見つかりません: {exp_file_path}")
                return None
            
            # Excelファイルを読み込み
            df = pd.read_excel(exp_file_path)
            
            if df.empty:
                self.ai_response_display.append(f"[ERROR] {data_source_name}ファイルは空のデータフレームです")
                return None
            
            # 課題番号列の存在確認とマッピング（データソースによって異なる）
            if use_arim_data:
                # ARIM実験データの場合は'ARIM ID'列を課題番号として使用
                if "ARIM ID" not in df.columns:
                    self.ai_response_display.append(f"[ERROR] ARIM実験データに'ARIM ID'列が見つかりません")
                    self.ai_response_display.append(f"利用可能な列: {list(df.columns)}")
                    return None
                # ARIM IDを課題番号列としてマッピング
                df['課題番号'] = df['ARIM ID']
                logger.debug("ARIM ID列を課題番号列にマッピングしました")
            else:
                # 標準実験データの場合は'課題番号'列を確認
                if "課題番号" not in df.columns:
                    self.ai_response_display.append(f"[ERROR] 標準実験データに'課題番号'列が見つかりません")
                    self.ai_response_display.append(f"利用可能な列: {list(df.columns)}")
                    return None
            
            # DataFrameをJSON形式に変換
            experiments = df.to_dict('records')
            
            self.ai_response_display.append(f"[INFO] {data_source_name}を読み込み完了: {len(experiments)} 件")
            logger.debug("一括分析用データ読み込み完了: %s 件", len(experiments))
            return experiments
            
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] 実験データの読み込みに失敗: {e}")
            return None
    
    def _load_material_index(self):
        """マテリアルインデックス（MI.json）を読み込み"""
        try:
            import os
            import json
            
            mi_file_path = get_dynamic_file_path("input/ai/MI.json")
            if not os.path.exists(mi_file_path):
                self.ai_response_display.append(f"[ERROR] マテリアルインデックスファイルが見つかりません: {mi_file_path}")
                return None
            
            with open(mi_file_path, 'r', encoding='utf-8') as f:
                mi_data = json.load(f)
            
            self.ai_response_display.append(f"[INFO] マテリアルインデックスを読み込み完了: {len(mi_data)} カテゴリ")
            return mi_data
            
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] マテリアルインデックスの読み込みに失敗: {e}")
            return None
    
    def _load_prompt_template(self, prompt_file="material_index.txt"):
        """プロンプトテンプレートを読み込み（ファイル名指定対応）"""
        try:
            import os
            
            prompt_file_path = os.path.join(INPUT_DIR, "ai", "prompts", prompt_file)
            if not os.path.exists(prompt_file_path):
                self.ai_response_display.append(f"[ERROR] プロンプトテンプレートファイルが見つかりません: {prompt_file_path}")
                return None
            
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            self.ai_response_display.append(f"[INFO] プロンプトテンプレートを読み込み完了: {prompt_file}")
            return template
            
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] プロンプトテンプレートの読み込みに失敗: {e}")
            return None
    
    def _validate_ai_settings_for_analysis(self):
        """
        Phase 2 Step 2.7.1: AI設定・バリデーション層の分離
        マテリアルインデックス分析用のAI設定確認
        """
        provider = self.ai_provider_combo.currentText()
        model = self.ai_model_combo.currentText()
        
        if provider == "設定なし":
            self.ai_response_display.append("[ERROR] AIプロバイダーが設定されていません")
            return False
            
        # プロバイダーとモデルを一時的にインスタンス変数として保存
        self._current_provider = provider
        self._current_model = model
        return True
    
    def _load_analysis_data(self):
        """
        Phase 2 Step 2.7.2: データ読み込み制御層の分離
        マテリアルインデックス分析用のデータ読み込み統合制御
        """
        # 実験データの読み込み
        exp_data = self._load_experiment_data()
        if not exp_data:
            self.hide_progress()
            self.ai_response_display.append("[ERROR] 実験データの読み込みに失敗しました")
            return None
        
        self.update_progress(35, 100, "マテリアルインデックス読み込み中...")
        
        # マテリアルインデックスの読み込み
        mi_data = self._load_material_index()
        if not mi_data:
            self.hide_progress()
            self.ai_response_display.append("[ERROR] マテリアルインデックスの読み込みに失敗しました")
            return None
        
        self.update_progress(50, 100, "プロンプトテンプレート読み込み中...")
        
        # プロンプトテンプレートの読み込み
        prompt_template = self._load_prompt_template("material_index.txt")
        if not prompt_template:
            self.hide_progress()
            self.ai_response_display.append("[ERROR] プロンプトテンプレートの読み込みに失敗しました")
            return None
        
        return {
            'exp_data': exp_data,
            'mi_data': mi_data,
            'prompt_template': prompt_template
        }
    
    def refresh_task_ids(self):
        """課題番号リストを更新"""
        try:
            # ai_response_displayが利用可能かチェック
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append("[INFO] 課題番号リストを更新中...")
            else:
                logger.info("課題番号リストを更新中...")
            
            # 実験データの読み込み
            exp_data = self._load_experiment_data_for_task_list()
            if not exp_data:
                error_msg = "[ERROR] 実験データの読み込みに失敗しました"
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(error_msg)
                else:
                    print(error_msg)
                return
            
            # 課題番号の抽出と集計
            task_summary = {}
            
            # データソースを確認
            use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                           self.arim_exp_radio.isChecked() and 
                           self.arim_exp_radio.isEnabled())
            
            for exp in exp_data:
                task_id = exp.get("課題番号", "")
                if task_id and task_id.strip():
                    task_id = task_id.strip()
                    if task_id not in task_summary:
                        # データソースに応じて適切な列から課題名を取得
                        if use_arim_data:
                            sample_title = exp.get("タイトル", "不明")
                        else:
                            sample_title = exp.get("課題名", "不明")
                        
                        task_summary[task_id] = {
                            'count': 0,
                            'sample_title': sample_title,
                            'sample_purpose': exp.get("目的", exp.get("概要", "不明"))
                        }
                    task_summary[task_id]['count'] += 1
            
            # コンボボックスの更新（コンボボックスが存在する場合のみ）
            logger.debug("hasattr(self, 'task_id_combo'): %s", hasattr(self, 'task_id_combo'))
            if hasattr(self, 'task_id_combo'):
                logger.debug("self.task_id_combo: %s", self.task_id_combo)
                logger.debug("task_id_combo is not None: %s", self.task_id_combo is not None)
                logger.debug("task_id_combo bool value: %s", bool(self.task_id_combo))
                try:
                    logger.debug("task_id_combo.isVisible(): %s", self.task_id_combo.isVisible())
                    logger.debug("task_id_combo.isEnabled(): %s", self.task_id_combo.isEnabled())
                except Exception as e:
                    logger.debug("task_id_combo状態確認エラー: %s", e)
            
            if hasattr(self, 'task_id_combo') and self.task_id_combo is not None:
                self.task_id_combo.clear()
                logger.debug("コンボボックスをクリア後の項目数: %s", self.task_id_combo.count())
                task_items = []
                
                if task_summary:
                    # 課題番号順にソート
                    sorted_tasks = sorted(task_summary.items())
                    
                    for task_id, info in sorted_tasks:
                        # 表示形式: "課題番号 (件数) - 課題名"
                        display_text = f"{task_id} ({info['count']}件) - {info['sample_title']}"
                        task_items.append(display_text)
                        self.task_id_combo.addItem(display_text, task_id)  # データとして実際の課題番号を保存
                        logger.debug("コンボボックスにアイテム追加: %s", display_text)
                    
                    logger.debug("コンボボックス項目数: %s", self.task_id_combo.count())
                    logger.debug("コンプリーター項目数: %s", len(task_items))
                    
                    # UIの強制更新
                    self.task_id_combo.update()
                    self.task_id_combo.repaint()
                    
                    # 確認のため最初の数項目を表示
                    logger.debug("コンボボックス内容確認:")
                    for i in range(min(3, self.task_id_combo.count())):
                        item_text = self.task_id_combo.itemText(i)
                        item_data = self.task_id_combo.itemData(i)
                        logger.debug("  [%s] text: '%s', data: '%s'", i, item_text, item_data)
                    
                    # オートコンプリート用のモデルを更新
                    if hasattr(self, 'task_completer') and self.task_completer:
                        from qt_compat.core import QStringListModel
                        completer_model = QStringListModel(task_items)
                        self.task_completer.setModel(completer_model)
                        # ポップアップの設定
                        popup_view = self.task_completer.popup()
                        popup_view.setMinimumHeight(200)
                        popup_view.setMaximumHeight(200)
                    
                    # デフォルト値を設定
                    default_task = "JPMXP1222TU0014"
                    for i in range(self.task_id_combo.count()):
                        if self.task_id_combo.itemData(i) == default_task:
                            self.task_id_combo.setCurrentIndex(i)
                            break
                    else:
                        # デフォルト値が見つからない場合は最初の項目を選択
                        if self.task_id_combo.count() > 0:
                            self.task_id_combo.setCurrentIndex(0)
                    
                    success_msg = f"[SUCCESS] 課題番号リストを更新: {len(task_summary)} 件"
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(success_msg)
                    else:
                        print(success_msg)
                else:
                    self.task_id_combo.addItem("課題番号が見つかりません", "")
                    warning_msg = "[WARNING] 有効な課題番号が見つかりませんでした"
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(warning_msg)
                    else:
                        print(warning_msg)
            else:
                # コンボボックスが存在しない場合は、データのみ確認
                logger.debug("コンボボックスが存在しないため、UIは更新されません")
                success_msg = f"[SUCCESS] 実験データを確認: {len(task_summary)} 種類の課題番号"
                print(success_msg)
                
        except Exception as e:
            error_msg = f"[ERROR] 課題番号リストの更新に失敗: {e}"
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(error_msg)
            else:
                print(error_msg)
            
            # エラー時のフォールバック処理
            if hasattr(self, 'task_id_combo') and self.task_id_combo:
                self.task_id_combo.clear()
                self.task_id_combo.addItem("エラー: データ読み込み失敗", "")
    
    def _load_experiment_data_for_task(self, task_id):
        """特定の課題ID用の実験データを読み込み"""
        # AIDataManagerに移行：既存の処理をAIDataManagerに委譲
        try:
            # データソース選択を確認
            use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                           self.arim_exp_radio.isChecked() and 
                           self.arim_exp_radio.isEnabled())
            
            # AIDataManagerを使用して特定課題の実験データを取得
            experiments = self.ai_data_manager.get_experiments_for_task(task_id, use_arim_data)
            
            # DataFrameとして返す（既存コードとの互換性のため）
            if experiments:
                import pandas as pd
                return pd.DataFrame(experiments)
            else:
                return None
                
        except Exception as e:
            error_msg = f"[ERROR] 課題別実験データ読み込み中にエラーが発生: {e}"
            print(error_msg)
            return None
    
    def _load_experiment_data_for_task_list(self):
        """課題番号リスト用の実験データを読み込み（データソース選択対応版）"""
        # AIDataManagerに移行：既存の処理をAIDataManagerに委譲
        try:
            # データソース選択を確認
            use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                           self.arim_exp_radio.isChecked() and 
                           self.arim_exp_radio.isEnabled())
            
            logger.debug("_load_experiment_data_for_task_list - use_arim_data: %s", use_arim_data)
            
            # AIDataManagerを使用してデータを読み込み
            experiments = self.ai_data_manager.load_experiment_data_file(use_arim_data)
            
            # 結果をそのまま返す（AIDataManagerで既に辞書形式に変換済み）
            return experiments
            
        except Exception as e:
            error_msg = f"[ERROR] 実験データ読み込み処理中にエラーが発生: {e}"
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(error_msg)
            else:
                print(error_msg)
            return None
    
    def _safe_string_length(self, value):
        """安全に文字列の長さを取得（float NaN対応）"""
        try:
            logger.debug("_safe_string_length called with: %s (type: %s)", repr(value), type(value))
            
            if value is None:
                logger.debug("Value is None, returning 0")
                return 0
            
            # pandas NaN チェック
            import pandas as pd
            if pd.isna(value):
                logger.debug("Value is pd.isna, returning 0")
                return 0
            
            # 文字列に変換
            str_value = str(value).strip()
            result = len(str_value)
            logger.debug("str_value: %s, length: %s", repr(str_value), result)
            return result
            
        except Exception as e:
            logger.debug("Error in _safe_string_length with value %s: %s", repr(value), e)
            import traceback
            traceback.print_exc()
            return 0

    def _is_valid_data_value(self, value):
        """データ値が有効かどうかを判定（nan、空値、未設定などを除外）"""
        # 親クラス（UIControllerCore）のai_data_managerを使用
        if hasattr(self, 'ai_data_manager') and self.ai_data_manager:
            return self.ai_data_manager.is_valid_data_value(value)
        
        # フォールバック処理（AIDataManagerが利用できない場合）
        import pandas as pd
        if value is None or pd.isna(value):
            return False
        if isinstance(value, str):
            str_value = value.strip()
            return str_value != "" and str_value.lower() != "nan"
        try:
            str_value = str(value).strip()
            return str_value != "" and str_value.lower() != "nan"
        except:
            return False

    def _get_all_experiments_for_task(self, task_id):
        """特定の課題IDに関連するすべての実験データを取得（AI分析一括処理用）"""
        # AIDataManagerに移行：既存の処理をAIDataManagerに委譲
        try:
            logger.debug("_get_all_experiments_for_task called with task_id: %s", task_id)
            
            # データソース選択を確認
            use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                           self.arim_exp_radio.isChecked() and 
                           self.arim_exp_radio.isEnabled())
            
            # AIDataManagerを使用して実験データを取得
            experiments = self.ai_data_manager.get_experiments_for_task(task_id, use_arim_data)
            
            if experiments is None:
                logger.error("実験データの読み込みに失敗")
                return []
                
            logger.debug("実験データ数: %s", len(experiments))
            
            # 有効なデータのみをフィルタリング
            valid_experiments = []
            for exp in experiments:
                if self._has_any_valid_experiment_data(exp):
                    valid_experiments.append(exp)
            
            logger.debug("有効な実験データ数: %s", len(valid_experiments))
            return valid_experiments
            
        except Exception as e:
            logger.error("_get_all_experiments_for_task エラー: %s", e)
            import traceback
            traceback.print_exc()
            return []
    
    def _has_any_valid_experiment_data(self, experiment):
        """実験データに何らかの有効な情報があるかどうかを判定（両データ形式対応）"""
        try:
            logger.debug("_has_any_valid_experiment_data called for experiment: %s", experiment.get('ARIM ID', experiment.get('実験ID', 'No ID')))
            
            # データソースを確認
            use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                           self.arim_exp_radio.isChecked() and 
                           self.arim_exp_radio.isEnabled())
            
            logger.debug("use_arim_data: %s", use_arim_data)
            
            if use_arim_data:
                # ARIM実験データの場合の必須列
                essential_columns = [
                    "タイトル", "概要", "分野", "キーワード",
                    "ナノ課題データ", "MEMS課題データ", "実験データ詳細",
                    "利用装置", "必要性コメント", "緊急性コメント",
                    "申請分野", "所属機関区分"
                ]
            else:
                # 標準実験データの場合の必須列
                essential_columns = [
                    "課題名", "目的", "研究概要目的と内容", "研究概要",
                    "施設・設備", "測定装置", "測定条件", "試料名",
                    "実験内容", "コメント", "備考", "説明", "実験データ",
                    "実験名", "測定名", "実験ID", "実験実施日"
                ]
            
            logger.debug("Checking %s essential columns", len(essential_columns))
            
            for col in essential_columns:
                try:
                    value = experiment.get(col)
                    logger.debug("Checking column '%s': %s (type: %s)", col, repr(value), type(value))
                    
                    if self._is_valid_data_value(value):
                        logger.debug("Found valid data in column '%s', returning True", col)
                        return True
                        
                except Exception as col_error:
                    logger.debug("Error checking column '%s': %s", col, col_error)
                    continue
            
            logger.debug("No valid data found in any essential column, returning False")
            return False
            
        except Exception as e:
            logger.debug("Error in _has_any_valid_experiment_data: %s", e)
            import traceback
            traceback.print_exc()
            return False
    
    def on_task_id_changed(self, text):
        """課題番号が変更された時の処理"""
        try:
            logger.debug("on_task_id_changed called with text: '%s'", text)
            
            # 重複呼び出し防止のためのフラグチェック
            if hasattr(self, '_updating_task_info') and self._updating_task_info:
                logger.debug("Already updating task info, skipping duplicate call")
                return
                
            # 必要なコンポーネントの安全な存在確認
            if not hasattr(self, 'task_id_combo'):
                logger.debug("task_id_combo attribute does not exist")
                return
                
            if not self.task_id_combo:
                logger.debug("task_id_combo is None")
                return
                
            # コンボボックスが初期化されているか確認
            try:
                if not self.task_id_combo.isVisible():
                    logger.debug("task_id_combo is not visible yet")
                    return
            except Exception as e:
                logger.debug("Error checking visibility: %s", e)
                return
                
            try:
                # コンボボックスの状態確認
                combo_count = self.task_id_combo.count()
                logger.debug("task_id_combo count: %s", combo_count)
                if combo_count == 0:
                    logger.debug("task_id_combo is empty, skipping update")
                    return
            except Exception as e:
                logger.debug("Error checking combo state: %s", e)
                return
                
            self._updating_task_info = True
            
            try:
                # 現在選択されている課題番号の詳細情報を取得
                current_index = self.task_id_combo.currentIndex()
                logger.debug("current_index: %s", current_index)
                
                if current_index >= 0:
                    task_id = self.task_id_combo.itemData(current_index)
                    logger.debug("task_id from itemData: '%s'", task_id)
                    
                    if task_id:
                        # 選択された課題番号の詳細情報を表示
                        self._update_task_info_display(task_id)
                        
                        # 実験データリストを更新
                        self._update_experiment_list(task_id)
                    else:
                        logger.debug("task_id is empty or None")
                        self._clear_task_info_display()
                else:
                    logger.debug("current_index is negative")
                    self._clear_task_info_display()
                    
            finally:
                self._updating_task_info = False
                
        except Exception as e:
            logger.error("on_task_id_changed failed: %s", e)
            import traceback
            traceback.print_exc()
            
            # エラー時もフラグをリセット
            if hasattr(self, '_updating_task_info'):
                self._updating_task_info = False

    def _update_task_info_display(self, task_id):
        """課題情報表示を更新"""
        try:
            import pandas as pd

            exp_data = self._load_experiment_data_for_task_list()
            logger.debug("exp_data loaded: %s records", len(exp_data) if exp_data else 0)
            
            if exp_data:
                matching_experiments = [exp for exp in exp_data if exp.get("課題番号") == task_id]
                logger.debug("matching_experiments for '%s': %s records", task_id, len(matching_experiments))
                
                if matching_experiments:
                    sample_exp: dict = matching_experiments[0]  # 型ヒント追加
                    info_lines = []
                    info_lines.append(f"📊 実験データ件数: {len(matching_experiments)}件")
                    
                    # データソースに応じて表示する項目を変更
                    use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                                   self.arim_exp_radio.isChecked() and 
                                   self.arim_exp_radio.isEnabled())
                    
                    if use_arim_data:
                        # ARIM実験データの場合
                        title_val = sample_exp.get("タイトル")
                        if title_val:
                            info_lines.append(f"📝 タイトル: {title_val}")
                        
                        summary_val = sample_exp.get("概要")
                        if summary_val:
                            if summary_val and not pd.isna(summary_val):
                                summary = str(summary_val).strip()
                                if summary:
                                    if len(summary) > 80:
                                        summary = summary[:80] + "..."
                                    info_lines.append(f"🎯 概要: {summary}")
                        
                        field_val = sample_exp.get("分野")
                        if field_val:
                            info_lines.append(f"🔬 分野: {field_val}")
                        
                        device_val = sample_exp.get("利用装置")
                        if device_val and not pd.isna(device_val):
                            device = str(device_val).strip()
                            if device:
                                if len(device) > 50:
                                    device = device[:50] + "..."
                                info_lines.append(f"🔧 利用装置: {device}")
                    else:
                        # 標準実験データの場合
                        task_name_val = sample_exp.get("課題名")
                        if task_name_val:
                            info_lines.append(f"📝 課題名: {task_name_val}")
                        
                        purpose_val = sample_exp.get("目的")
                        if purpose_val:
                            if purpose_val and not pd.isna(purpose_val):
                                purpose = str(purpose_val).strip()
                                if purpose:
                                    if len(purpose) > 80:
                                        purpose = purpose[:80] + "..."
                                    info_lines.append(f"🎯 目的: {purpose}")
                        
                        facility_val = sample_exp.get("施設・設備")
                        if facility_val and not pd.isna(facility_val):
                            facility = str(facility_val).strip()
                            if facility:
                                info_lines.append(f"� 施設・設備: {facility}")
                    
                    # 課題情報の表示を更新
                    info_text = "\n".join(info_lines)
                    if hasattr(self, 'task_info_label') and self.task_info_label:
                        self.task_info_label.setText(info_text)
                        
                else:
                    self._clear_task_info_display()
            else:
                self._clear_task_info_display()
                
        except Exception as e:
            logger.error("_update_task_info_display failed: %s", e)
            self._clear_task_info_display()

    def _clear_task_info_display(self):
        """課題情報表示をクリア"""
        try:
            if hasattr(self, 'task_info_label') and self.task_info_label:
                self.task_info_label.setText("課題番号を選択してください")
        except Exception as e:
            logger.error("_clear_task_info_display failed: %s", e)

    def _update_experiment_list(self, task_id):
        """実験データリストを更新"""
        try:
            import pandas as pd
            
            if not hasattr(self, 'experiment_combo') or not self.experiment_combo:
                logger.debug("experiment_combo is not available")
                return
                
            # 実験データリストをクリア
            self.experiment_combo.clear()
            
            # 選択された課題に対応する実験データを取得
            exp_data = self._load_experiment_data_for_task(task_id)
            
            if exp_data is not None and not exp_data.empty:
                # 実験データが存在する場合
                valid_experiments_count = 0
                for idx, row in exp_data.iterrows():
                    arim_id = row.get("ARIM ID", "")
                    title = row.get("タイトル", "未設定")
                    experiment_date = row.get("実験日", "未設定")
                    equipment = row.get("実験装置", "未設定")
                    
                    # 空値や NaN の処理
                    if pd.isna(title) or str(title).strip() == "":
                        title = "未設定"
                    if pd.isna(experiment_date) or str(experiment_date).strip() == "":
                        experiment_date = "未設定"
                    if pd.isna(equipment) or str(equipment).strip() == "":
                        equipment = "未設定"
                    
                    # 実験データの有効性チェック
                    has_valid_content = False
                    content_fields = ["概要", "実験データ詳細", "利用装置", "装置仕様", "手法", "測定条件"]
                    for field in content_fields:
                        value = row.get(field)
                        if value and not pd.isna(value) and str(value).strip() != "" and str(value).strip().lower() != "nan":
                            has_valid_content = True
                            break
                    
                    # 表示テキストを詳細に構成
                    display_text = f"ARIM ID: {arim_id} | タイトル: {title} | 実験日: {experiment_date} | 装置: {equipment}"
                    if not has_valid_content:
                        display_text += " [⚠️ 内容不足]"
                    
                    # データを辞書形式で保存
                    experiment_data = {
                        "課題番号": task_id,
                        "ARIM ID": arim_id,
                        "実験データ種別": "実験データあり",
                        "_has_valid_content": has_valid_content  # 内部検証フラグ
                    }
                    
                    # その他の列も追加
                    for col in exp_data.columns:
                        if col not in experiment_data:
                            experiment_data[col] = row.get(col, "")
                    
                    self.experiment_combo.addItem(display_text, experiment_data)
                    if has_valid_content:
                        valid_experiments_count += 1
                
                # 実験データなしのオプションも追加
                no_data_text = "実験データなし"
                no_data_dict = {
                    "課題番号": task_id,
                    "ARIM ID": "",
                    "実験データ種別": "実験データなし",
                    "_has_valid_content": False
                }
                self.experiment_combo.addItem(no_data_text, no_data_dict)
                
                logger.debug("Added %s experiments (%s valid) + 1 no-data option", len(exp_data), valid_experiments_count)
            else:
                # 実験データが存在しない場合
                no_data_text = "実験データなし（課題のみ）"
                no_data_dict = {
                    "課題番号": task_id,
                    "ARIM ID": "",
                    "実験データ種別": "実験データなし",
                    "_has_valid_content": False
                }
                self.experiment_combo.addItem(no_data_text, no_data_dict)
                logger.debug("No experiment data found, added no-data option only")
            
            # 最初の項目を選択（実験データありを優先）
            if self.experiment_combo.count() > 0:
                # 有効な実験データがある場合は最初の有効なデータを選択
                selected_index = 0
                for i in range(self.experiment_combo.count()):
                    item_data = self.experiment_combo.itemData(i)
                    if (item_data and 
                        item_data.get("実験データ種別") == "実験データあり" and 
                        item_data.get("_has_valid_content", False)):
                        selected_index = i
                        break
                
                self.experiment_combo.setCurrentIndex(selected_index)
                logger.debug("Selected experiment index: %s", selected_index)
                
        except Exception as e:
            logger.error("_update_experiment_list failed: %s", e)
            import traceback
            traceback.print_exc()
            
            # エラー時は安全なデフォルト状態を設定
            try:
                if hasattr(self, 'experiment_combo') and self.experiment_combo:
                    self.experiment_combo.clear()
                    self.experiment_combo.addItem("課題番号を選択してください", None)
            except:
                pass

    def on_task_index_changed(self, index):
        """課題番号のインデックスが変更された時の処理（ドロップダウン選択対応）"""
        try:
            logger.debug("on_task_index_changed called with index: %s", index)
            
            if not hasattr(self, 'task_id_combo') or not self.task_id_combo:
                logger.debug("task_id_combo is not available in index changed")
                return
                
            if index >= 0:
                # インデックスから対応するテキストを取得
                text = self.task_id_combo.itemText(index)
                logger.debug("Index %s corresponds to text: '%s'", index, text)
                
                # テキストが変更されていない場合は手動で更新処理を呼び出し
                current_text = self.task_id_combo.currentText()
                if text == current_text:
                    logger.debug("Text matches current text, manually triggering update")
                    self.on_task_id_changed(text)
                
        except Exception as e:
            logger.debug("Error in on_task_index_changed: %s", e)
    
    def on_completer_activated(self, text):
        """コンプリーターから選択された時の処理"""
        try:
            logger.debug("on_completer_activated called with text: '%s'", text)
            
            # 短い遅延の後に更新処理を実行（UIの更新を待つため）
            self._schedule_qt_single_shot(100, lambda: self.on_task_id_changed(text), key="on_task_id_changed_delayed")
            
        except Exception as e:
            logger.debug("Error in on_completer_activated: %s", e)
    
    def _update_experiment_choices(self, task_id, experiments):
        """実験データ選択肢を更新"""
        try:
            logger.debug("_update_experiment_choices called with task_id='%s', experiments count=%s", task_id, len(experiments) if experiments else 0)
            
            # experiment_comboの存在確認
            if not hasattr(self, 'experiment_combo') or not self.experiment_combo:
                logger.debug("experiment_combo is not available")
                return
                
            # コンボボックスをクリア
            self.experiment_combo.clear()
            logger.debug("experiment_combo cleared")
            
            # 実験データが存在する場合
            if experiments:
                logger.debug("Processing %s experiments", len(experiments))
                
                # 有効な実験データのみをフィルタリング
                valid_experiments = []
                for i, exp in enumerate(experiments):
                    try:
                        exp_id = exp.get('実験ID', exp.get('ARIM ID', f'Exp{i+1}'))
                        logger.debug("Checking experiment %s/%s: %s", i+1, len(experiments), exp_id)
                        
                        if self._has_any_valid_experiment_data(exp):
                            valid_experiments.append(exp)
                            logger.debug("Experiment %s is valid, added to list", exp_id)
                        else:
                            logger.debug("Skipping experiment with no valid data: %s", exp_id)
                    except Exception as exp_error:
                        logger.debug("Error checking experiment validity for %s: %s", exp.get('実験ID', exp.get('ARIM ID', f'Exp{i+1}')), exp_error)
                        import traceback
                        traceback.print_exc()
                        # エラーがあっても処理を続行
                        continue
                
                logger.debug("Valid experiments count: %s", len(valid_experiments))
                
                if valid_experiments:
                    # データソースを確認
                    use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                                   self.arim_exp_radio.isChecked() and 
                                   self.arim_exp_radio.isEnabled())
                    
                    for i, exp in enumerate(valid_experiments):
                        try:
                            exp_id = exp.get('実験ID', exp.get('ARIM ID', f'Exp{i+1}'))
                            logger.debug("Processing experiment %s: %s", i+1, exp_id)
                            
                            # 表示用のテキストを作成
                            display_text = f"[{i+1}] "
                            
                            # データソースに応じて主要内容を取得
                            if use_arim_data:
                                # ARIM実験データの場合
                                main_content = self._get_safe_display_content_arim(exp)
                            else:
                                # 標準実験データの場合
                                main_content = self._get_safe_display_content_standard(exp)
                            
                            display_text += main_content
                            
                            # 追加情報を取得
                            additional_info = self._get_safe_additional_info(exp, use_arim_data)
                            if additional_info:
                                display_text += f" ({additional_info})"
                            
                            # コンボボックスに追加
                            self.experiment_combo.addItem(display_text, exp)
                            logger.debug("Added experiment item: %s", display_text)
                            
                        except Exception as exp_error:
                            logger.debug("Error processing experiment %s: %s", i+1, exp_error)
                            # エラーがあってもフォールバック表示を追加
                            try:
                                fallback_text = f"[{i+1}] 実験データ {i+1} (表示エラー)"
                                self.experiment_combo.addItem(fallback_text, exp)
                                logger.debug("Added fallback experiment item: %s", fallback_text)
                            except:
                                logger.debug("Failed to add fallback item for experiment %s", i+1)
                                continue
                    
                    # 実験選択UI要素を表示
                    self.experiment_combo.setVisible(True)
                    if hasattr(self, 'experiment_info_label'):
                        self.experiment_info_label.setVisible(True)
                        
                    # 最初の実験を選択状態にして詳細表示
                    if len(valid_experiments) > 0:
                        self.experiment_combo.setCurrentIndex(0)
                        try:
                            self._update_experiment_info(valid_experiments[0])
                        except Exception as info_error:
                            logger.debug("Error updating experiment info: %s", info_error)
                else:
                    logger.debug("No valid experiments found, clearing choices")
                    self._clear_experiment_choices()
                
            else:
                logger.debug("No experiments data provided, clearing choices")
                self._clear_experiment_choices()
                
        except Exception as main_error:
            error_message = f"実験データ選択でエラーが発生: {str(main_error)}"
            logger.error("%s", error_message)
            
            # GUIにエラーメッセージを表示
            if hasattr(self, 'ai_response_display'):
                self.ai_response_display.append(f"[ERROR] {error_message}")
            
            # トレースバック出力
            import traceback
            traceback.print_exc()
            
            # フォールバック処理
            try:
                self._clear_experiment_choices()
            except:
                logger.debug("Failed to clear experiment choices in error handling")

    def _get_safe_display_content_arim(self, exp):
        """ARIM実験データの安全な表示内容取得"""
        try:
            logger.debug("_get_safe_display_content_arim called")
            
            # ARIM IDを優先表示（識別用）
            arim_id = exp.get("ARIM ID", "")
            logger.debug("arim_id: %s", repr(arim_id))
            
            # タイトルまたは概要から主要内容を取得
            title_val = exp.get("タイトル")
            gaiyo_val = exp.get("概要")
            
            logger.debug("title_val: %s (type: %s)", repr(title_val), type(title_val))
            logger.debug("gaiyo_val: %s (type: %s)", repr(gaiyo_val), type(gaiyo_val))
            
            # ARIM IDが有効な場合は、それを基本とする
            if self._is_valid_data_value(arim_id):
                main_content = str(arim_id).strip()
                
                # タイトルが利用可能な場合は簡潔に追加
                if self._is_valid_data_value(title_val):
                    title_str = str(title_val).strip()
                    title_len = self._safe_string_length(title_str)
                    if title_len > 25:
                        title_str = title_str[:25] + "..."
                    main_content += f" - {title_str}"
            else:
                # ARIM IDが無効な場合はタイトルまたは概要を使用
                if self._is_valid_data_value(title_val):
                    logger.debug("Using title_val")
                    main_content = str(title_val).strip()
                elif self._is_valid_data_value(gaiyo_val):
                    logger.debug("Using gaiyo_val")
                    main_content = str(gaiyo_val).strip()
                else:
                    main_content = "タイトル不明"
                
                # 長い場合は切り詰め
                content_len = self._safe_string_length(main_content)
                if content_len > 35:
                    main_content = main_content[:35] + "..."
            
            logger.debug("main_content: %s", repr(main_content))
            logger.debug("Returning: %s", repr(main_content))
            return main_content
                
        except Exception as e:
            logger.debug("Error in _get_safe_display_content_arim: %s", e)
            import traceback
            traceback.print_exc()
            return "データ取得エラー"

    def _get_safe_display_content_standard(self, exp):
        """標準実験データの安全な表示内容取得"""
        try:
            # 課題番号を優先表示（識別用）
            task_number = exp.get("課題番号", "")
            
            # 課題名、目的、または研究概要から主要内容を取得
            data_columns = ["課題名", "目的", "研究概要目的と内容", "研究概要"]
            title_content = ""
            
            for col in data_columns:
                if self._is_valid_data_value(exp.get(col)):
                    title_content = str(exp[col]).strip()
                    break
            
            # 課題番号が有効な場合は、それを基本とする
            if self._is_valid_data_value(task_number):
                main_content = str(task_number).strip()
                
                # 課題名が利用可能な場合は簡潔に追加
                if title_content:
                    title_len = self._safe_string_length(title_content)
                    if title_len > 25:
                        title_content = title_content[:25] + "..."
                    main_content += f" - {title_content}"
            else:
                # 課題番号が無効な場合は課題名等を使用
                if title_content:
                    content_len = self._safe_string_length(title_content)
                    if content_len > 35:
                        main_content = title_content[:35] + "..."
                    else:
                        main_content = title_content
                else:
                    main_content = "課題名不明"
            
            return main_content
                
        except Exception as e:
            logger.debug("Error in _get_safe_display_content_standard: %s", e)
            return "データ取得エラー"

    def _get_safe_additional_info(self, exp, use_arim_data):
        """安全な追加情報取得（実験名、装置名、実験日を含む）"""
        try:
            additional_info = []
            
            if use_arim_data:
                # ARIM実験データの場合
                # 1. 実験名（タイトル）を追加
                title_val = exp.get("タイトル")
                if self._is_valid_data_value(title_val):
                    title_info = str(title_val).strip()
                    title_len = self._safe_string_length(title_info)
                    if title_len > 30:
                        title_info = title_info[:30] + "..."
                    additional_info.append(f"実験名: {title_info}")
                
                # 2. 装置名を追加（実験装置を優先、次に利用装置）
                device_info = ""
                exp_device_val = exp.get("実験装置")
                use_device_val = exp.get("利用装置")
                
                if self._is_valid_data_value(exp_device_val):
                    device_info = str(exp_device_val).strip()
                elif self._is_valid_data_value(use_device_val):
                    device_info = str(use_device_val).strip()
                
                if device_info:
                    # 装置名をクリーンアップ（::を除去）
                    device_info = device_info.replace('::', '').strip()
                    if device_info:
                        device_len = self._safe_string_length(device_info)
                        if device_len > 25:
                            device_info = device_info[:25] + "..."
                        additional_info.append(f"装置: {device_info}")
                
                # 3. 実験日を追加
                exp_date_val = exp.get("実験日")
                year_val = exp.get("年度")
                
                if self._is_valid_data_value(exp_date_val):
                    date_info = str(exp_date_val).strip()
                    additional_info.append(f"実験日: {date_info}")
                elif self._is_valid_data_value(year_val):
                    additional_info.append(f"年度: {str(year_val).strip()}")
            else:
                # 標準実験データの場合
                # 1. 実験名（課題名）を追加
                task_name_val = exp.get("課題名")
                if self._is_valid_data_value(task_name_val):
                    task_name_info = str(task_name_val).strip()
                    task_name_len = self._safe_string_length(task_name_info)
                    if task_name_len > 30:
                        task_name_info = task_name_info[:30] + "..."
                    additional_info.append(f"課題名: {task_name_info}")
                
                # 2. 装置名（施設・設備）を追加
                if self._is_valid_data_value(exp.get("施設・設備")):
                    device_info = str(exp["施設・設備"]).strip()
                    device_len = self._safe_string_length(device_info)
                    if device_len > 25:
                        device_info = device_info[:25] + "..."
                    additional_info.append(f"装置: {device_info}")
                
                # 3. 実験実施日を追加
                if self._is_valid_data_value(exp.get("実験実施日")):
                    date_info = str(exp['実験実施日']).strip()
                    additional_info.append(f"実施日: {date_info}")
            
            return " | ".join(additional_info)  # 区切り文字を"|"に変更してより読みやすく
            
        except Exception as e:
            logger.debug("Error in _get_safe_additional_info: %s", e)
            return ""
    
    def _clear_experiment_choices(self):
        """実験データ選択肢をクリア"""
        try:
            logger.debug("_clear_experiment_choices called")
            if hasattr(self, 'experiment_combo') and self.experiment_combo:
                self.experiment_combo.clear()
                self.experiment_combo.addItem("課題番号を選択してください", None)
                logger.debug("experiment_combo cleared and reset to placeholder")
                
            if hasattr(self, 'experiment_info_label') and self.experiment_info_label:
                self.experiment_info_label.setText("課題番号を選択すると、該当する実験データが表示されます。")
                logger.debug("experiment_info_label reset to placeholder")
                
        except Exception as e:
            logger.error("実験選択肢クリアエラー: %s", e)
    
    def _clear_experiment_choices_safe(self):
        """実験データ選択肢をクリア（安全版）"""
        try:
            logger.debug("_clear_experiment_choices_safe called")
            if hasattr(self, 'experiment_combo') and self.experiment_combo is not None:
                try:
                    self.experiment_combo.clear()
                    self.experiment_combo.addItem("課題番号を選択してください", None)
                    logger.debug("experiment_combo safely cleared and reset")
                except Exception as e:
                    logger.debug("Error clearing experiment_combo: %s", e)
                
            if hasattr(self, 'experiment_info_label') and self.experiment_info_label is not None:
                try:
                    self.experiment_info_label.setText("課題番号を選択すると、該当する実験データが表示されます。")
                    logger.debug("experiment_info_label safely reset")
                except Exception as e:
                    logger.debug("Error clearing experiment_info_label: %s", e)
                
        except Exception as e:
            logger.error("実験選択肢安全クリアエラー: %s", e)
    
    def on_experiment_changed(self, index):
        """実験データが変更された時の処理"""
        try:
            if not hasattr(self, 'experiment_combo') or not self.experiment_combo:
                return
                
            if index >= 0:
                experiment_data = self.experiment_combo.itemData(index)
                if experiment_data:
                    self._update_experiment_info(experiment_data)
                else:
                    if hasattr(self, 'experiment_info_label'):
                        self.experiment_info_label.setText("実験データが無効です")
            else:
                if hasattr(self, 'experiment_info_label'):
                    self.experiment_info_label.setText("")
                    
        except Exception as e:
            logger.error("実験変更処理エラー: %s", e)
            if hasattr(self, 'experiment_info_label'):
                self.experiment_info_label.setText(f"エラー: {e}")
    
    def _update_experiment_info(self, experiment):
        """選択された実験の詳細情報を表示（データソース対応版）"""
        try:
            if not hasattr(self, 'experiment_info_label') or not self.experiment_info_label:
                return
                
            info_lines = []
            
            # データソースを確認
            use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                           self.arim_exp_radio.isChecked() and 
                           self.arim_exp_radio.isEnabled())
            
            # 基本情報（データソースに応じて表示項目を変更）
            if use_arim_data:
                # ARIM実験データの場合 - 主要情報を最初に表示
                if self._is_valid_data_value(experiment.get("タイトル")):
                    info_lines.append(f"📝 タイトル: {str(experiment['タイトル']).strip()}")
                else:
                    info_lines.append("📝 タイトル: 未設定")
                
                if self._is_valid_data_value(experiment.get("実験日")):
                    info_lines.append(f"📅 実験日: {str(experiment['実験日']).strip()}")
                else:
                    info_lines.append("📅 実験日: 未設定")
                
                if self._is_valid_data_value(experiment.get("実験装置")):
                    info_lines.append(f"🔧 実験装置: {str(experiment['実験装置']).strip()}")
                elif self._is_valid_data_value(experiment.get("利用装置")):
                    info_lines.append(f"🔧 利用装置: {str(experiment['利用装置']).strip()}")
                else:
                    info_lines.append("🔧 実験装置: 未設定")
                
                info_lines.append("─" * 30)
                
                if self._is_valid_data_value(experiment.get("ARIM ID")):
                    info_lines.append(f"🔢 ARIM ID: {str(experiment['ARIM ID']).strip()}")
                
                if self._is_valid_data_value(experiment.get("課題番号")):
                    info_lines.append(f"📋 課題番号: {str(experiment['課題番号']).strip()}")
                
                if self._is_valid_data_value(experiment.get("年度")):
                    info_lines.append(f"📅 年度: {str(experiment['年度']).strip()}")
                
                if self._is_valid_data_value(experiment.get("課題クラス")):
                    info_lines.append(f"📊 課題クラス: {str(experiment['課題クラス']).strip()}")
                
                if self._is_valid_data_value(experiment.get("申請者番号")):
                    info_lines.append(f"👤 申請者番号: {str(experiment['申請者番号']).strip()}")
                
                if self._is_valid_data_value(experiment.get("所属機関区分")):
                    info_lines.append(f"🏢 所属機関区分: {str(experiment['所属機関区分']).strip()}")
            else:
                # 標準実験データの場合 - 主要情報を最初に表示
                if self._is_valid_data_value(experiment.get("課題名")):
                    info_lines.append(f"📝 課題名: {str(experiment['課題名']).strip()}")
                else:
                    info_lines.append("📝 課題名: 未設定")
                
                if self._is_valid_data_value(experiment.get("実験実施日")):
                    info_lines.append(f"� 実験実施日: {str(experiment['実験実施日']).strip()}")
                else:
                    info_lines.append("📅 実験実施日: 未設定")
                
                if self._is_valid_data_value(experiment.get("測定装置")):
                    info_lines.append(f"🔧 測定装置: {str(experiment['測定装置']).strip()}")
                else:
                    info_lines.append("🔧 測定装置: 未設定")
                
                info_lines.append("─" * 30)
                
                if self._is_valid_data_value(experiment.get("実験ID")):
                    info_lines.append(f"🔢 実験ID: {str(experiment['実験ID']).strip()}")
                
                if self._is_valid_data_value(experiment.get("施設・設備")):
                    info_lines.append(f"🏢 施設・設備: {str(experiment['施設・設備']).strip()}")
                
                if self._is_valid_data_value(experiment.get("試料名")):
                    info_lines.append(f"🧪 試料名: {str(experiment['試料名']).strip()}")
            
            # セパレータを追加
            if info_lines:
                info_lines.append("─" * 30)
            
            # 実際のデータ列内容をコメント表示
            info_lines.append("💬 データ内容:")
            
            # データソースに応じてデータ列を選択
            if use_arim_data:
                # ARIM実験データの場合
                data_columns = {
                    "タイトル": "📝 タイトル",
                    "概要": "📖 概要",
                    "分野": "🔬 分野",
                    "キーワード": "🏷️ キーワード",
                    "利用装置": "🔧 利用装置",
                    "ナノ課題データ": "📊 ナノ課題データ",
                    "MEMS課題データ": "📊 MEMS課題データ",
                    "実験データ詳細": "📋 実験データ詳細",
                    "必要性コメント": "💭 必要性コメント",
                    "緊急性コメント": "⚡ 緊急性コメント"
                }
            else:
                # 標準実験データの場合
                data_columns = {
                    "目的": "🎯 目的",
                    "研究概要目的と内容": "📖 研究概要",
                    "研究概要": "📖 研究概要", 
                    "測定条件": "⚙️ 測定条件",
                    "実験内容": "📋 実験内容", 
                    "コメント": "💭 コメント",
                    "備考": "📝 備考",
                    "説明": "📖 説明",
                    "実験データ": "📊 実験データ"
                }
            
            displayed_any_data = False
            for col, label in data_columns.items():
                if self._is_valid_data_value(experiment.get(col)):
                    content = str(experiment[col]).strip()
                    # 長い内容は複数行に分割して表示
                    if len(content) > 80:
                        # 80文字ごとに改行
                        lines = [content[i:i+80] for i in range(0, len(content), 80)]
                        info_lines.append(f"{label}:")
                        for line in lines:
                            info_lines.append(f"  {line}")
                    else:
                        info_lines.append(f"{label}: {content}")
                    displayed_any_data = True
            
            if not displayed_any_data:
                info_lines.append("  データ内容が見つかりません")
            
            info_text = "\n".join(info_lines) if info_lines else "詳細情報なし"
            self.experiment_info_label.setText(info_text)
            
        except Exception as e:
            logger.error("実験情報更新エラー: %s", e)
            if hasattr(self, 'experiment_info_label'):
                self.experiment_info_label.setText(f"情報取得エラー: {e}")
    
    def show_arim_extension_popup(self):
        """ARIM拡張情報をポップアップ表示（選択された課題番号に対応）"""
        try:
            # 選択された課題番号を取得
            selected_task_id = None
            
            # 修正: ai_controllerのcurrent_ai_test_widgetを参照
            ai_test_widget = None
            if hasattr(self, 'ai_controller') and hasattr(self.ai_controller, 'current_ai_test_widget'):
                ai_test_widget = self.ai_controller.current_ai_test_widget
            elif hasattr(self, 'ai_test_widget'):
                ai_test_widget = self.ai_test_widget
                
            if ai_test_widget:
                if hasattr(ai_test_widget, 'task_id_combo') and ai_test_widget.task_id_combo:
                    current_index = ai_test_widget.task_id_combo.currentIndex()
                    if current_index >= 0:
                        selected_task_id = ai_test_widget.task_id_combo.itemData(current_index)
                        
                        # itemDataから取得できない場合は、テキストから抽出
                        if not selected_task_id:
                            text = ai_test_widget.task_id_combo.currentText()
                            import re
                            match = re.match(r'^([A-Z0-9]+)', text.strip())
                            if match:
                                selected_task_id = match.group(1)
            
            logger.debug("show_arim_extension_popup: selected_task_id = %s", selected_task_id)
            
            # キャッシュされたデータがある場合はそれを使用、なければ新たに読み込み
            arim_data = None
            if hasattr(self, 'current_arim_data') and self.current_arim_data:
                arim_data = self.current_arim_data
            else:
                arim_data = self._load_arim_extension_data()
            
            content_lines = [
                "=== ARIM拡張情報 ===",
                f"チェックボックス状態: {'✅ 有効' if hasattr(self, 'arim_extension_checkbox') and self.arim_extension_checkbox.isChecked() else '❌ 無効'}",
                "",
            ]
            
            if not selected_task_id:
                content_lines.extend([
                    "❌ 課題番号が選択されていません",
                    "",
                    "課題番号選択ドロップダウンから課題を選択してください。",
                ])
            elif not arim_data:
                content_lines.extend([
                    f"選択された課題番号: {selected_task_id}",
                    "❌ ARIM拡張データが見つかりません",
                    "",
                    "以下を確認してください:",
                    "• INPUT_DIR/ai/arim/converted.xlsx ファイルが存在するか",
                    "• pandas がインストールされているか", 
                    "• ファイルの読み込み権限があるか",
                    "• ARIMNO列または課題番号列が含まれているか",
                ])
            else:
                # 選択された課題番号に対応するデータを取得
                matching_records = []
                
                # 1. ARIMNO列での完全一致検索（優先）
                for record in arim_data:
                    arimno = record.get('ARIMNO', '')
                    if arimno and str(arimno) == str(selected_task_id):
                        matching_records.append(record)
                
                # 2. 課題番号列での完全一致検索
                if not matching_records:
                    for record in arim_data:
                        kadai_no = record.get('課題番号', '')
                        if kadai_no and str(kadai_no) == str(selected_task_id):
                            matching_records.append(record)
                
                content_lines.extend([
                    f"選択された課題番号: {selected_task_id}",
                    f"マッチングレコード数: {len(matching_records)} 件",
                    f"全体データ件数: {len(arim_data)} 件", 
                    f"ファイル: INPUT_DIR/ai/arim/converted.xlsx",
                    "",
                    "=== 検索方式 ===",
                    "1. ARIMNO列での完全一致検索（優先）",
                    "2. 課題番号列での完全一致検索",
                    "",
                ])
                
                if matching_records:
                    content_lines.append(f"=== {selected_task_id} に対応するARIM拡張データ ===")
                    for i, record in enumerate(matching_records, 1):
                        content_lines.append(f"\n--- レコード {i} ---")
                        for key, value in record.items():
                            if value is not None and str(value).strip():  # 空でない値のみ表示
                                content_lines.append(f"{key}: {value}")
                else:
                    content_lines.extend([
                        f"❌ 課題番号 {selected_task_id} に対応するARIM拡張データが見つかりません",
                        "",
                        "以下の検索を実行しました:",
                        f"• ARIMNO列での完全一致: {selected_task_id}",
                        f"• 課題番号列での完全一致: {selected_task_id}",
                        "",
                        "注意: 完全一致検索のみ実行（末尾4桁検索は無効化済み）"
                    ])
            
            content = "\n".join(content_lines)
            popup = PopupDialog(self.parent, "ARIM拡張情報", content)
            popup.exec_()
                
        except Exception as e:
            content = f"=== ARIM拡張情報 ===\n\n❌ エラーが発生しました:\n{e}"
            popup = PopupDialog(self.parent, "ARIM拡張情報", content)
            popup.exec_()
    
    def show_request_popup(self):
        """最後のリクエスト内容をポップアップ表示"""
        try:
            # デバッグ情報を追加
            has_attr = hasattr(self, 'last_request_content')
            content_exists = has_attr and bool(self.last_request_content)
            content_length = len(self.last_request_content) if has_attr else 0
            
            logger.debug("show_request_popup: has_attr=%s, content_exists=%s, length=%s", has_attr, content_exists, content_length)
            
            if content_exists:
                # ARIM拡張情報が含まれているかチェック（正しいセクション名で検索）
                arim_section_marker = "【拡張実験情報（ARIM拡張含む）】"
                has_arim_extension = arim_section_marker in self.last_request_content
                arim_count = self.last_request_content.count(arim_section_marker)
                
                # より詳細なARIM関連検索
                arim_keywords = [
                    "ARIM拡張情報",
                    "ARIM拡張",
                    "拡張実験情報",
                    arim_section_marker
                ]
                arim_keyword_counts = {keyword: self.last_request_content.count(keyword) for keyword in arim_keywords}
                
                content = f"=== 最後のAIリクエスト内容 ===\n"
                content += f"文字数: {content_length} 文字\n"
                content += f"保存時刻: {getattr(self, 'last_request_time', '不明')}\n"
                content += f"ARIM拡張情報: {'含まれています' if has_arim_extension else '含まれていません'}\n"
                
                if has_arim_extension:
                    content += f"【拡張実験情報（ARIM拡張含む）】セクション出現回数: {arim_count} 回\n"
                    
                # ARIM関連キーワードの詳細
                content += f"ARIM関連キーワード検出:\n"
                for keyword, count in arim_keyword_counts.items():
                    if count > 0:
                        content += f"  • '{keyword}': {count} 回\n"
                        
                # 拡張実験情報セクションの内容を抽出して表示
                if has_arim_extension:
                    import re
                    # 【拡張実験情報（ARIM拡張含む）】セクションを抽出
                    pattern = r"【拡張実験情報（ARIM拡張含む）】\s*(.*?)(?=【|$)"
                    matches = re.findall(pattern, self.last_request_content, re.DOTALL)
                    if matches:
                        arim_section_content = matches[0].strip()
                        content += f"拡張実験情報セクション内容長: {len(arim_section_content)} 文字\n"
                        # ARIM拡張情報が実際に含まれているかチェック
                        has_actual_arim_data = "【ARIM拡張情報" in arim_section_content
                        content += f"実際のARIM拡張データ: {'含まれています' if has_actual_arim_data else '含まれていません'}\n"
                
                content += "\n" + "="*50 + "\n\n"
                content += self.last_request_content
            else:
                content = "=== AIリクエスト内容 ===\n\n"
                content += "❌ 表示可能なリクエスト内容がありません\n\n"
                content += f"デバッグ情報:\n"
                content += f"• has_attr: {has_attr}\n"
                content += f"• content_exists: {content_exists}\n"
                content += f"• content_length: {content_length}\n\n"
                content += "AI分析を実行してからもう一度お試しください。"
            
            popup = PopupDialog(self.parent, "リクエスト内容", content)
            popup.exec_()
            
        except Exception as e:
            content = f"=== リクエスト内容 ===\n\n❌ エラーが発生しました:\n{e}"
            popup = PopupDialog(self.parent, "リクエスト内容", content)
            popup.exec_()
    
    def show_response_popup(self):
        """AIレスポンス内容をポップアップ表示"""
        try:
            if hasattr(self, 'ai_result_display') and self.ai_result_display.toPlainText():
                content = "=== AIレスポンス内容 ===\n\n"
                
                # レスポンス情報を追加表示
                if hasattr(self, 'last_response_info') and self.last_response_info:
                    info = self.last_response_info
                    content += f"📊 モデル: {info.get('model', '不明')}\n"
                    content += f"⏱️ 応答時間: {info.get('response_time', 0):.2f}秒\n"
                    
                    if info.get('usage'):
                        usage = info['usage']
                        if isinstance(usage, dict):
                            if 'total_tokens' in usage:
                                content += f"🪙 トークン使用量: {usage['total_tokens']}\n"
                            elif 'totalTokens' in usage:
                                content += f"🪙 トークン使用量: {usage['totalTokens']}\n"
                        else:
                            content += f"🪙 使用量: {usage}\n"
                    
                    if info.get('analysis_type'):
                        content += f"🔍 分析タイプ: {info['analysis_type']}\n"
                    if info.get('batch_info'):
                        content += f"📦 バッチ情報: {info['batch_info']}\n"
                    
                    if not info.get('success', True):
                        content += f"❌ エラー: {info.get('error', '不明なエラー')}\n"
                    
                    content += "\n" + "="*50 + "\n\n"
                
                content += self.ai_result_display.toPlainText()
            else:
                content = "=== AIレスポンス内容 ===\n\n❌ 表示可能なレスポンス内容がありません\n\nAI分析を実行してからもう一度お試しください。"
            
            popup = PopupDialog(self.parent, "レスポンス内容", content)
            popup.exec_()
            
        except Exception as e:
            content = f"=== レスポンス内容 ===\n\n❌ エラーが発生しました:\n{e}"
            popup = PopupDialog(self.parent, "レスポンス内容", content)
            popup.exec_()

    def show_task_info_popup(self):
        """課題詳細情報をポップアップ表示"""
        try:
            # AIテストウィジェットのtask_info_labelから情報を取得
            task_info_text = ""
            current_task = ""
            
            # 修正: ai_controllerのcurrent_ai_test_widgetを参照
            ai_test_widget = None
            if hasattr(self, 'ai_controller') and hasattr(self.ai_controller, 'current_ai_test_widget'):
                ai_test_widget = self.ai_controller.current_ai_test_widget
            elif hasattr(self, 'ai_test_widget'):
                ai_test_widget = self.ai_test_widget
                
            logger.debug("show_task_info_popup: ai_test_widget = %s", ai_test_widget)
            
            if ai_test_widget:
                logger.debug("show_task_info_popup: ai_test_widget exists")
                logger.debug("show_task_info_popup: hasattr(ai_test_widget, 'task_info_label')=%s", hasattr(ai_test_widget, 'task_info_label'))
                
                # AIテストウィジェットのtask_info_labelから取得
                if hasattr(ai_test_widget, 'task_info_label') and ai_test_widget.task_info_label:
                    task_info_text = ai_test_widget.task_info_label.text()
                    logger.debug("show_task_info_popup: ai_test_widget.task_info_label.text()='%s'", task_info_text)
                else:
                    logger.debug("show_task_info_popup: ai_test_widget.task_info_label not available")
                    
                # 現在選択されている課題番号を取得
                if hasattr(ai_test_widget, 'task_id_combo') and ai_test_widget.task_id_combo:
                    current_task = ai_test_widget.task_id_combo.currentText()
                    current_index = ai_test_widget.task_id_combo.currentIndex()
                    current_data = ai_test_widget.task_id_combo.itemData(current_index) if current_index >= 0 else None
                    logger.debug("show_task_info_popup: ai_test_widget.task_id_combo.currentText()='%s'", current_task)
                    logger.debug("show_task_info_popup: ai_test_widget.task_id_combo.currentIndex()=%s", current_index)
                    logger.debug("show_task_info_popup: ai_test_widget.task_id_combo.itemData()='%s'", current_data)
                else:
                    logger.debug("show_task_info_popup: ai_test_widget.task_id_combo not available")
            else:
                logger.debug("show_task_info_popup: ai_test_widget not available")
            
            # フォールバック: 通常のtask_info_labelも確認
            if not task_info_text and hasattr(self, 'task_info_label') and self.task_info_label:
                task_info_text = self.task_info_label.text()
                logger.debug("show_task_info_popup: fallback task_info_label.text()='%s'", task_info_text)
                
            # フォールバック: 通常のtask_id_comboも確認
            if not current_task and hasattr(self, 'task_id_combo') and self.task_id_combo:
                current_task = self.task_id_combo.currentText()
                logger.debug("show_task_info_popup: fallback task_id_combo.currentText()='%s'", current_task)
            
            logger.debug("show_task_info_popup: final task_info_text='%s', current_task='%s'", task_info_text, current_task)
            
            if task_info_text and task_info_text not in ["課題番号を選択してください", ""]:
                content = "=== 選択した課題の詳細情報 ===\n\n"
                
                if current_task:
                    # 課題番号の表示形式から課題番号部分を抽出
                    import re
                    match = re.match(r'^([A-Z0-9]+)', current_task.strip())
                    if match:
                        task_id = match.group(1)
                        content += f"📋 課題番号: {task_id}\n\n"
                    else:
                        content += f"📋 課題番号: {current_task}\n\n"
                
                # 課題情報の内容を追加
                content += task_info_text
                
            else:
                content = "=== 課題詳細情報 ===\n\n❌ 表示可能な課題情報がありません\n\n課題番号を選択してからもう一度お試しください。"
            
            # TextAreaExpandDialogを使用してポップアップ表示
            dialog = TextAreaExpandDialog(self.parent, "課題詳細情報", content, False, None)
            dialog.show()
            
        except Exception as e:
            logger.error("show_task_info_popup: %s", e)
            import traceback
            logger.error("show_task_info_popup traceback: %s", traceback.format_exc())
            content = f"=== 課題詳細情報 ===\n\n❌ エラーが発生しました:\n{e}"
            dialog = TextAreaExpandDialog(self.parent, "課題詳細情報", content, False, None)
            dialog.show()

    def show_experiment_info_popup(self):
        """実験データ詳細情報をポップアップ表示"""
        try:
            # AIテストウィジェットから実験データ情報を取得
            experiment_info_text = ""
            current_experiment = ""
            
            # 修正: ai_controllerのcurrent_ai_test_widgetを参照
            ai_test_widget = None
            if hasattr(self, 'ai_controller') and hasattr(self.ai_controller, 'current_ai_test_widget'):
                ai_test_widget = self.ai_controller.current_ai_test_widget
            elif hasattr(self, 'ai_test_widget'):
                ai_test_widget = self.ai_test_widget
                
            logger.debug("show_experiment_info_popup: ai_test_widget = %s", ai_test_widget)
            
            if ai_test_widget:
                logger.debug("show_experiment_info_popup: ai_test_widget exists")
                
                # AIテストウィジェットのexperiment_info_labelから取得
                if hasattr(ai_test_widget, 'experiment_info_label') and ai_test_widget.experiment_info_label:
                    experiment_info_text = ai_test_widget.experiment_info_label.text()
                    logger.debug("show_experiment_info_popup: ai_test_widget.experiment_info_label.text()='%s...'", experiment_info_text[:100])
                else:
                    logger.debug("show_experiment_info_popup: ai_test_widget.experiment_info_label not available")
                    
                # 現在選択されている実験データを取得
                if hasattr(ai_test_widget, 'experiment_combo') and ai_test_widget.experiment_combo:
                    current_experiment = ai_test_widget.experiment_combo.currentText()
                    current_index = ai_test_widget.experiment_combo.currentIndex()
                    current_data = ai_test_widget.experiment_combo.itemData(current_index) if current_index >= 0 else None
                    logger.debug("show_experiment_info_popup: ai_test_widget.experiment_combo.currentText()='%s'", current_experiment)
                    logger.debug("show_experiment_info_popup: ai_test_widget.experiment_combo.currentIndex()=%s", current_index)
                    logger.debug("show_experiment_info_popup: ai_test_widget.experiment_combo.itemData()='%s'", current_data)
                else:
                    logger.debug("show_experiment_info_popup: ai_test_widget.experiment_combo not available")
            else:
                logger.debug("show_experiment_info_popup: ai_test_widget not available")
            
            # フォールバック: 通常のexperiment_info_labelも確認
            if not experiment_info_text and hasattr(self, 'experiment_info_label') and self.experiment_info_label:
                experiment_info_text = self.experiment_info_label.text()
                logger.debug("show_experiment_info_popup: fallback experiment_info_label.text()='%s...'", experiment_info_text[:100])
                
            # フォールバック: 通常のexperiment_comboも確認
            if not current_experiment and hasattr(self, 'experiment_combo') and self.experiment_combo:
                current_experiment = self.experiment_combo.currentText()
                logger.debug("show_experiment_info_popup: fallback experiment_combo.currentText()='%s'", current_experiment)
            
            logger.debug("show_experiment_info_popup: final experiment_info_text='%s...', current_experiment='%s'", experiment_info_text[:100] if experiment_info_text else '', current_experiment)
            
            if experiment_info_text and experiment_info_text not in ["課題番号を選択すると、該当する実験データが表示されます。", ""]:
                content = "=== 選択した実験データの詳細情報 ===\n\n"
                
                if current_experiment:
                    content += f"🧪 実験データ: {current_experiment}\n\n"
                
                # 実験情報の内容を追加
                content += experiment_info_text
                
            else:
                content = "=== 実験データ詳細情報 ===\n\n❌ 表示可能な実験データ情報がありません\n\n課題番号と実験データを選択してからもう一度お試しください。"
            
            # TextAreaExpandDialogを使用してポップアップ表示
            dialog = TextAreaExpandDialog(self.parent, "実験データ詳細情報", content, False, None)
            dialog.show()
            
        except Exception as e:
            logger.error("show_experiment_info_popup: %s", e)
            import traceback
            logger.error("show_experiment_info_popup traceback: %s", traceback.format_exc())
            content = f"=== 実験データ詳細情報 ===\n\n❌ エラーが発生しました:\n{e}"
            dialog = TextAreaExpandDialog(self.parent, "実験データ詳細情報", content, False, None)
            dialog.show()

    def on_analysis_method_changed(self, index):
        """分析方法が変更された時の処理"""
        logger.debug("ui_controller.on_analysis_method_changed called with index: %s", index)
        try:
            if index >= 0 and hasattr(self, 'analysis_method_combo'):
                logger.debug("analysis_method_combo exists, getting item data for index %s", index)
                method_data = self.analysis_method_combo.itemData(index)
                logger.debug("method_data: %s", method_data)
                if method_data and hasattr(self, 'analysis_description_label'):
                    logger.debug("analysis_description_label exists, updating text")
                    description = method_data.get("description", "")
                    exec_type = method_data.get("exec_type", "SINGLE")
                    data_methods = method_data.get("data_methods", [])
                    static_files = method_data.get("static_files", [])
                    
                    # 拡張説明を作成
                    extended_description = f"{description}"
                    if exec_type == "MULTI":
                        extended_description += "\n🔄 実行タイプ: 一括処理（全実験データをループ処理）"
                    else:
                        extended_description += "\n🎯 実行タイプ: 単体処理（選択された実験データのみ）"
                    
                    if data_methods:
                        extended_description += f"\n📊 データ取得: {', '.join(data_methods)}"
                    
                    if static_files:
                        extended_description += f"\n📁 静的データ: {', '.join(static_files)}"
                    
                    self.analysis_description_label.setText(extended_description)
                    logger.debug("analysis_description_label updated with: %s...", extended_description[:100])
                    
                    # 単体処理の場合は実験データ選択が必要であることを強調
                    if exec_type == "SINGLE":
                        final_text = f"{extended_description}\n⚠️ 単体の実験データを選択してください"
                        self.analysis_description_label.setText(final_text)
                        logger.debug("Single exec type warning added")
                else:
                    logger.debug("method_data is None or analysis_description_label missing")
            else:
                logger.debug("Invalid index (%s) or analysis_method_combo missing", index)
                        
        except Exception as e:
            logger.error("分析方法変更処理エラー: %s", e)
            import traceback
            traceback.print_exc()
            if hasattr(self, 'analysis_description_label'):
                self.analysis_description_label.setText(f"エラー: {e}")

    # =============================
    # フォールバック メソッド（分離クラス使用に失敗した場合用）
    # =============================
    
    def _create_ai_test_widget(self):
        """AIテスト機能用のウィジェットを作成（AIコントローラーに委譲）"""
        # AI設定を確実に初期化
        if not hasattr(self, 'ai_manager') or self.ai_manager is None:
            self._init_ai_settings()
        return self.ai_controller.create_ai_test_widget()
    
    # =============================
    # データ取得メソッド（拡張AI分析システム用）
    # =============================
    
    # =============================
    # Basic Info メソッド（basicパッケージ委譲）
    # =============================
    
    def fetch_basic_info(self):
        """基本情報取得(ALL) - basicパッケージに委譲"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_basic_info
            fetch_basic_info(self)
        except ImportError as e:
            self.show_error(f"基本情報モジュールのインポートに失敗しました: {e}")
        except Exception as e:
            self.show_error(f"基本情報取得でエラーが発生しました: {e}")
    
    def fetch_basic_info_self(self):
        """基本情報取得(検索) - basicパッケージに委譲"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_basic_info_self
            fetch_basic_info_self(self)
        except ImportError as e:
            self.show_error(f"基本情報モジュールのインポートに失敗しました: {e}")
        except Exception as e:
            self.show_error(f"基本情報取得(検索)でエラーが発生しました: {e}")
    
    def fetch_common_info_only(self):
        """共通情報のみ取得 - basicパッケージに委譲"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_common_info_only
            fetch_common_info_only(self)
        except ImportError as e:
            self.show_error(f"基本情報モジュールのインポートに失敗しました: {e}")
        except Exception as e:
            self.show_error(f"共通情報取得でエラーが発生しました: {e}")

    def fetch_common_info_only2(self):
        """共通情報取得2 - 取得対象選択付き（basicパッケージに委譲）"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_common_info_only2
            fetch_common_info_only2(self)
        except ImportError as e:
            self.show_error(f"基本情報モジュールのインポートに失敗しました: {e}")
        except Exception as e:
            self.show_error(f"共通情報取得2でエラーが発生しました: {e}")
    
    def fetch_invoice_schema(self):
        """invoice_schema取得 - basicパッケージに委譲"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_invoice_schema
            fetch_invoice_schema(self)
        except ImportError as e:
            self.show_error(f"基本情報モジュールのインポートに失敗しました: {e}")
        except Exception as e:
            self.show_error(f"invoice_schema取得でエラーが発生しました: {e}")
    
    def fetch_sample_info_only(self):
        """サンプル情報強制取得 - basicパッケージに委譲"""
        try:
            from classes.basic.ui.ui_basic_info import fetch_sample_info_only
            fetch_sample_info_only(self)
        except ImportError as e:
            self.show_error(f"基本情報モジュールのインポートに失敗しました: {e}")
        except Exception as e:
            self.show_error(f"サンプル情報取得でエラーが発生しました: {e}")
    
    def _create_fallback_settings_widget(self):
        """フォールバック：従来の設定ダイアログを開くボタンを含むウィジェット"""
        from qt_compat.widgets import QWidget, QVBoxLayout, QPushButton, QLabel
        from qt_compat.core import Qt
        
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(20)
        
        # メッセージラベル
        message_label = QLabel("設定機能の読み込み中にエラーが発生しました。\n従来の設定画面を開いてください。")
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 14px; padding: 20px;")
        layout.addWidget(message_label)
        
        # 設定ダイアログを開くボタン
        open_settings_button = QPushButton("設定画面を開く")
        open_settings_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                min-width: 120px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)};
            }}
        """)
        
        def open_legacy_settings():
            """従来の設定ダイアログを開く"""
            try:
                from classes.config.ui.settings_dialog import run_settings_logic
                parent_widget = self.parent
                bearer_token = getattr(parent_widget, 'bearer_token', None)
                run_settings_logic(parent_widget, bearer_token)
            except Exception as e:
                logger.error("設定ダイアログオープンエラー: %s", e)
        
        open_settings_button.clicked.connect(open_legacy_settings)
        layout.addWidget(open_settings_button)
        
        return widget
    
    def _apply_initial_data_register_sizing(self):
        """初回のデータ登録ウィジェット作成時にウィンドウサイズを95%に設定"""
        try:
            from qt_compat.widgets import QApplication
            from qt_compat.core import QTimer
            
            # 通常登録タブの初期サイズ (90%高さ、標準幅1200px)
            def apply_sizing():
                if hasattr(self, 'parent') and self.parent:
                    screen = QApplication.primaryScreen().geometry()
                    target_height = int(screen.height() * 0.90)
                    target_width = 1200  # 通常登録タブの標準幅
                    
                    logger.debug("初回データ登録ウィジェット作成: 画面サイズ適用 %sx%s", target_width, target_height)
                    self.parent.resize(target_width, target_height)
                    # 位置調整は行わない（ユーザー要望により削除）
            
            # UIが完全に作成された後にサイズを適用
            self._schedule_qt_single_shot(50, apply_sizing, key="apply_initial_data_register_sizing")
            
        except Exception as e:
            logger.error("初回データ登録サイズ適用エラー: %s", e)
    
    def open_ai_extension_dialog_from_menu(self):
        """メニューからAI拡張ダイアログを直接開く（簡素化版）"""
        try:
            logger.debug("メニューからAI拡張ダイアログを開く")
            
            # AI拡張ダイアログを直接起動
            self._launch_ai_extension_dialog_direct()
            
        except Exception as e:
            logger.error("メニューからのAI拡張ダイアログ起動エラー: %s", e)
            import traceback
            traceback.print_exc()
            from qt_compat.widgets import QMessageBox
            QMessageBox.critical(None, "エラー", f"AI拡張機能の起動に失敗しました: {str(e)}")
    
    def open_help_dialog(self):
        """メニューからヘルプを開く（メインウィンドウ内に表示）"""
        try:
            logger.debug("ヘルプモードに切り替え")
            self.switch_mode("help")
            
        except Exception as e:
            logger.error("ヘルプ表示エラー: %s", e)
            import traceback
            traceback.print_exc()
            from qt_compat.widgets import QMessageBox
            QMessageBox.critical(None, "エラー", f"ヘルプの表示に失敗しました: {str(e)}")

    
    def _launch_ai_extension_dialog_direct(self):
        """AI拡張ダイアログを直接起動（簡素化版）"""
        try:
            AISuggestionDialog = self._get_ai_suggestion_dialog_class()
            
            logger.debug("AI拡張ダイアログを直接起動")
            
            # 基本的なコンテキストデータを作成
            context_data = {
                'name': '',
                'type': 'mixed', 
                'grant_number': '',
                'description': '',
                'access_policy': 'restricted',
                'contact': '',
                'dataset_id': ''
            }
            
            # ダイアログを作成（AI拡張モード）
            # NOTE: 親なしTop-levelにすると、pytest-qt等の長時間セッションで
            # close後の破棄タイミングが不安定になり、Qtネイティブクラッシュの
            # 要因になり得る。可能な限りメインウィンドウへ親付けする。
            dialog_parent = getattr(self, "parent", None)
            dialog = AISuggestionDialog(
                parent=dialog_parent,
                context_data=context_data,
                extension_name="dataset_description",
                auto_generate=False,
                mode="ai_extension"  # AI拡張モード: AI拡張、ファイル抽出設定タブのみ表示
            )

            try:
                from qt_compat.core import Qt

                dialog.setAttribute(Qt.WA_DeleteOnClose, True)
            except Exception:
                pass
            
            # AI拡張タブを選択
            if hasattr(dialog, 'tab_widget'):
                def select_extension_tab():
                    try:
                        for i in range(dialog.tab_widget.count()):
                            tab_text = dialog.tab_widget.tabText(i)
                            if "AI拡張" in tab_text:
                                dialog.tab_widget.setCurrentIndex(i)
                                logger.debug("AI拡張タブを選択: インデックス %s", i)
                                break
                    except Exception as e:
                        logger.error("AI拡張タブ選択エラー: %s", e)

                # ダイアログが閉じた後に発火しないよう、dialog を親にする
                try:
                    self._schedule_qt_single_shot(100, select_extension_tab, parent=dialog, key="select_ai_extension_tab")
                except Exception:
                    pass
            
            # ダイアログを表示
            dialog.show()
            logger.debug("AI拡張ダイアログ表示完了")
            
        except Exception as e:
            logger.error("AI拡張ダイアログ直接起動エラー: %s", e)
            import traceback
            traceback.print_exc()
            from qt_compat.widgets import QMessageBox
            QMessageBox.critical(None, "エラー", f"AI拡張ダイアログの起動に失敗しました: {str(e)}")
            import traceback
            traceback.print_exc()
    


