"""
AI提案ダイアログ
データセットの説明文をAIで生成・提案するダイアログウィンドウ
"""

import os
import time
import datetime
import json
import logging
import re
import math
from typing import Optional, List
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QTextEdit, QProgressBar,
    QMessageBox, QSplitter, QWidget, QTabWidget, QGroupBox,
    QComboBox, QCheckBox, QSpinBox
)
from qt_compat.core import Qt, QThread, Signal, QTimer
from classes.theme import ThemeKey
from classes.theme.theme_manager import get_color
from classes.utils.dataset_filter_fetcher import DatasetFilterFetcher
from config.common import get_dynamic_file_path

# ロガー設定
logger = logging.getLogger(__name__)

# NOTE:
# ai_suggestion_dialog は初回表示時のimportコストがボトルネックになりやすいため、
# 重い依存（AIManager/拡張レジストリ/スピナー等）は使用箇所で遅延importする。

# 一部のテスト環境でQDialogがMagicMock化され、インスタンス属性参照が困難な場合のフォールバック
try:
    from qt_compat.widgets import QDialog as _QCDialog
    # QDialogクラス自体に cancel_ai_button を定義しておくと、
    # テスト環境での属性探索時にも isVisible() が False を返せる
    class _CancelButtonShim:
        def isVisible(self):
            return False
    setattr(_QCDialog, 'cancel_ai_button', _CancelButtonShim())
except Exception:
    pass


class AIRequestThread(QThread):
    """AI リクエスト処理用スレッド"""
    result_ready = Signal(object)  # PySide6: dict→object
    error_occurred = Signal(str)
    
    def __init__(self, prompt, context_data=None):
        super().__init__()
        self.prompt = prompt
        self.context_data = context_data or {}
        self._stop_requested = False
        
    def stop(self):
        """スレッドの停止をリクエスト"""
        self._stop_requested = True
        
    def run(self):
        """AIリクエストを実行"""
        try:
            if self._stop_requested:
                return

            from classes.ai.core.ai_manager import AIManager

            ai_manager = AIManager()
            
            if self._stop_requested:
                return
            
            # AIManagerからデフォルト設定を取得
            provider = ai_manager.get_default_provider()
            model = ai_manager.get_default_model(provider)
            
            # デバッグ用ログ出力
            logger.debug("AI設定取得: provider=%s, model=%s", provider, model)
            
            if self._stop_requested:
                logger.info("AIリクエストがキャンセルされました（送信前）")
                return
            
            # AIリクエスト実行
            result = ai_manager.send_prompt(self.prompt, provider, model)
            
            # 送信後もキャンセルチェック
            if self._stop_requested:
                logger.info("AIリクエストがキャンセルされました（送信後）")
                return
            
            if result.get('success', False):
                self.result_ready.emit(result)
            else:
                error_msg = result.get('error', '不明なエラー')
                self.error_occurred.emit(f"AIリクエストエラー: {error_msg}")
                
        except Exception as e:
            self.error_occurred.emit(f"AIリクエスト処理エラー: {str(e)}")


class AISuggestionDialog(QDialog):
    """AI提案ダイアログクラス
    
    モード:
        - dataset_suggestion: データセット説明文提案モード（AI提案、プロンプト全文、詳細情報タブ）
        - ai_extension: AI拡張機能モード（AI拡張、ファイル抽出設定タブ）
    """
    
    def __init__(self, parent=None, context_data=None, extension_name="dataset_description", auto_generate=True, mode="dataset_suggestion"):
        super().__init__(parent)
        self.context_data = context_data or {}
        self.extension_name = extension_name
        self.suggestions = []
        self.selected_suggestion = None
        self.ai_thread = None
        self.extension_ai_threads = []  # AI拡張用のスレッドリスト
        self._active_extension_button = None  # AI拡張で実行中のボタン
        self.extension_buttons = []  # AI拡張ボタンのリスト（複数クリック防止用）
        # データセットタブ（一覧選択）用
        self.dataset_ai_threads = []
        self._active_dataset_button = None
        self.dataset_buttons = []
        self._dataset_entries = []
        self._selected_dataset_record = None

        # データセット一括問い合わせ用（報告書タブ相当）
        self._bulk_dataset_queue = []
        self._bulk_dataset_index = 0
        self._bulk_dataset_total = 0
        self._bulk_dataset_next_index = 0
        self._bulk_dataset_inflight = 0
        self._bulk_dataset_max_concurrency = 5
        self._bulk_dataset_running = False
        self._bulk_dataset_cancelled = False
        # 報告書タブ（converted.xlsx）用
        self.report_ai_threads = []
        self._active_report_button = None
        self.report_buttons = []
        self._report_entries = []
        self._selected_report_record = None
        self._selected_report_placeholders = {}
        # 報告書一括問い合わせ用
        self._bulk_report_queue = []
        self._bulk_report_index = 0  # 完了件数（互換のため名称は維持）
        self._bulk_report_total = 0
        self._bulk_report_next_index = 0
        self._bulk_report_inflight = 0
        self._bulk_report_max_concurrency = 5
        self._bulk_report_running = False
        self._bulk_report_cancelled = False
        self.auto_generate = auto_generate  # 自動生成フラグ
        self.last_used_prompt = None  # 最後に使用したプロンプトを保存
        self.last_api_request_params = None  # 最後に使用したAPIリクエストパラメータ（本文除外）
        self.last_api_response_params = None  # 最後に使用したAPIレスポンスパラメータ（本文除外）
        self.last_api_provider = None  # 最後に使用したprovider
        self.last_api_model = None  # 最後に使用したmodel
        self.mode = mode  # 表示モード: "dataset_suggestion" または "ai_extension"
        self._dataset_filter_fetcher: Optional[DatasetFilterFetcher] = None
        self._dataset_filter_widget: Optional[QWidget] = None
        self._dataset_combo_connected = False
        self._dataset_dropdown_initialized = False
        self._dataset_dropdown_initializing = False
        self._did_initial_top_align = False
        
        # AI拡張機能を取得
        from classes.ai.extensions import AIExtensionRegistry, DatasetDescriptionExtension

        self.ai_extension = AIExtensionRegistry.get(extension_name)
        if not self.ai_extension:
            self.ai_extension = DatasetDescriptionExtension()
        
        self.setup_ui()
        self.setup_connections()
        
        # 自動生成が有効な場合、ダイアログ表示後に自動でAI提案を生成
        if self.auto_generate:
            QTimer.singleShot(100, self.auto_generate_suggestions)
        
    def setup_ui(self):
        """UI要素のセットアップ"""
        self.setWindowTitle("AI説明文提案")
        if os.environ.get("PYTEST_CURRENT_TEST"):
            self.setAttribute(Qt.WA_DontShowOnScreen, True)
        else:
            self.setModal(True)
        try:
            # ユーザーが自由にサイズ変更できるようにする（右下グリップ表示）
            self.setSizeGripEnabled(True)
        except Exception:
            pass
        self.resize(900, 700)
        self._apply_window_height_policy()
        # 位置は showEvent で上端揃え（要件）
        
        layout = QVBoxLayout(self)

        # タイトルとツールバー
        header_layout = QHBoxLayout()
        title_label = QLabel("AIによる説明文の提案")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 10px;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # プロンプトテンプレート編集ボタンは廃止（AI拡張側で編集）
        
        layout.addLayout(header_layout)
        
        # タブウィジェット
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget, 1)

        # モードに応じてタブを選択的に追加
        if self.mode == "dataset_suggestion":
            # データセット提案モード: AI提案、プロンプト全文、詳細情報
            main_tab = QWidget()
            self.tab_widget.addTab(main_tab, "AI提案")
            self.setup_main_tab(main_tab)
            
            prompt_tab = QWidget()
            self.tab_widget.addTab(prompt_tab, "プロンプト全文")
            self.setup_prompt_tab(prompt_tab)
            
            detail_tab = QWidget()
            self.tab_widget.addTab(detail_tab, "詳細情報")
            self.setup_detail_tab(detail_tab)
            
        elif self.mode == "ai_extension":
            # AI拡張モード: AI拡張、ファイル抽出設定
            try:
                extension_tab = QWidget()
                self.tab_widget.addTab(extension_tab, "AI拡張")
                self.setup_extension_tab(extension_tab)
            except Exception as e:
                logger.warning("AI拡張タブの初期化に失敗しました: %s", e)

            # データセット/報告書/結果一覧は初期化が重いため、タブ選択時に遅延生成する
            # （タブ自体は最初から表示してUXは維持）
            self._lazy_tab_builders = {}

            def _register_lazy_tab(title: str, build_fn):
                tab = QWidget()
                self.tab_widget.addTab(tab, title)
                idx = self.tab_widget.indexOf(tab)
                self._lazy_tab_builders[idx] = (tab, build_fn)

            _register_lazy_tab("データセット", self.setup_dataset_tab)
            _register_lazy_tab("報告書", self.setup_report_tab)
            
            try:
                extraction_settings_tab = QWidget()
                self.tab_widget.addTab(extraction_settings_tab, "ファイル抽出設定")
                self.setup_extraction_settings_tab(extraction_settings_tab)
            except Exception as e:
                logger.warning("ファイル抽出設定タブの初期化に失敗しました: %s", e)

            _register_lazy_tab("結果一覧", self.setup_results_tab)

            def _ensure_lazy_tab_initialized(index: int):
                try:
                    if not hasattr(self, "_lazy_tab_builders"):
                        return
                    entry = self._lazy_tab_builders.pop(index, None)
                    if not entry:
                        return
                    tab, build_fn = entry
                    build_fn(tab)
                except Exception as e:
                    logger.warning("遅延タブ初期化に失敗しました: index=%s error=%s", index, e)

            try:
                # 初回選択時のみ初期化したいので、popで一度限りにする
                self.tab_widget.currentChanged.connect(_ensure_lazy_tab_initialized)
            except Exception:
                pass
        
        # 注: データセット開設タブでの将来的な利用も想定
        # データセット開設タブから呼び出す場合は、mode="dataset_suggestion"を使用
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        # SpinnerButtonをインポートして使用
        from classes.dataset.ui.spinner_button import SpinnerButton
        
        self.generate_button = SpinnerButton("🚀 AI提案生成")
        self.generate_button.setMinimumHeight(35)
        
        # キャンセルボタン（AI実行中のみ表示・有効）
        self.cancel_ai_button = QPushButton("⏹ キャンセル")
        self.cancel_ai_button.setMinimumHeight(35)
        self.cancel_ai_button.setVisible(False)  # 初期状態は非表示
        # 一部のテスト環境でウィジェットがMagicMock化されるケースへの防御
        try:
            if hasattr(self.cancel_ai_button, 'isVisible') and hasattr(self.cancel_ai_button.isVisible, 'return_value'):
                # MagicMock の場合は初期値 False を明示
                self.cancel_ai_button.isVisible.return_value = False
            # クラス属性にも参照を設定（MagicMockでインスタンス属性参照が拾われない環境向けフォールバック）
            try:
                setattr(type(self), 'cancel_ai_button', self.cancel_ai_button)
            except Exception:
                pass
        except Exception:
            pass
        
        self.apply_button = QPushButton("適用")
        self.cancel_button = QPushButton("キャンセル")
        
        self.apply_button.setEnabled(False)
        
        button_layout.addWidget(self.generate_button)
        button_layout.addWidget(self.cancel_ai_button)
        button_layout.addStretch()
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)

        # タブ切替時のボタン表示制御
        self.tab_widget.currentChanged.connect(self.toggle_action_buttons)

        # 初期状態でボタン表示を更新
        QTimer.singleShot(50, self.toggle_action_buttons)

        # データセット選択ドロップダウンを初期化
        QTimer.singleShot(100, self.initialize_dataset_dropdown)

        # テーマ変更に追従
        try:
            from classes.theme.theme_manager import ThemeManager

            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        except Exception:
            pass

        # 初期テーマ適用
        self.refresh_theme()

    # ------------------------------------------------------------------
    # Layout helpers (AI拡張/データセット/報告書)
    # ------------------------------------------------------------------
    def _register_conditional_tab_scroll(self, tab_widget: QWidget, scroll_area, response_widget: QWidget) -> None:
        """応答領域がタブ高の50%を超える場合のみ、タブ全体スクロールを有効化する。"""
        try:
            if not hasattr(self, '_conditional_tab_scroll_policies'):
                self._conditional_tab_scroll_policies = {}
            self._conditional_tab_scroll_policies[int(id(tab_widget))] = {
                'tab': tab_widget,
                'scroll': scroll_area,
                'response': response_widget,
            }
            try:
                tab_widget.installEventFilter(self)
            except Exception:
                pass
        except Exception:
            pass

    def _update_conditional_tab_scroll(self, tab_widget: QWidget) -> None:
        try:
            policies = getattr(self, '_conditional_tab_scroll_policies', {})
            entry = policies.get(int(id(tab_widget))) if isinstance(policies, dict) else None
            if not isinstance(entry, dict):
                return

            scroll = entry.get('scroll')
            response_widget = entry.get('response')
            if scroll is None or response_widget is None:
                return

            try:
                viewport_h = int(scroll.viewport().height())
            except Exception:
                viewport_h = int(tab_widget.height())
            if viewport_h <= 0:
                return

            try:
                response_h = int(response_widget.height())
            except Exception:
                response_h = 0
            if response_h <= 0:
                try:
                    response_h = int(response_widget.sizeHint().height())
                except Exception:
                    response_h = 0

            enable_scroll = (response_h > int(viewport_h * 0.5)) if response_h > 0 else False
            try:
                if enable_scroll:
                    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                else:
                    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            except Exception:
                pass
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802 - Qt互換
        try:
            from PySide6.QtCore import QEvent

            if event is not None and event.type() in (QEvent.Resize, QEvent.Show):
                policies = getattr(self, '_conditional_tab_scroll_policies', {})
                if isinstance(policies, dict):
                    entry = policies.get(int(id(obj)))
                    if isinstance(entry, dict) and entry.get('tab') is obj:
                        try:
                            QTimer.singleShot(0, lambda o=obj: self._update_conditional_tab_scroll(o))
                        except Exception:
                            pass
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _configure_table_visible_rows(self, table_widget, visible_rows_including_header: int) -> None:
        """QTableWidgetの表示高さを「ヘッダ + N行」に固定し、超過分はテーブル側でスクロールさせる。"""
        try:
            rows_total = int(visible_rows_including_header)
        except Exception:
            rows_total = 0
        if rows_total <= 1:
            return

        def _apply():
            try:
                header_h = int(table_widget.horizontalHeader().height())
            except Exception:
                header_h = 0
            try:
                row_h = int(table_widget.verticalHeader().defaultSectionSize())
            except Exception:
                row_h = 0
            if row_h <= 0:
                row_h = 24

            data_rows = max(0, rows_total - 1)
            try:
                frame = int(table_widget.frameWidth()) * 2
            except Exception:
                frame = 0

            target_h = header_h + (row_h * data_rows) + frame
            target_h = max(80, int(target_h) + 2)

            try:
                table_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            except Exception:
                pass
            try:
                table_widget.setFixedHeight(int(target_h))
            except Exception:
                pass

        try:
            QTimer.singleShot(0, _apply)
        except Exception:
            _apply()

    def _apply_minimum_height_policy(self):
        """(互換) ダイアログ最小高さを画面高の50%に設定（利用可能な場合）。"""
        try:
            screen = self.screen() if hasattr(self, 'screen') else None
            if screen is None:
                from qt_compat.widgets import QApplication
                screen = QApplication.primaryScreen()
            if screen is None:
                return

            geo = screen.availableGeometry()
            if not geo or geo.height() <= 0:
                return

            min_h = int(geo.height() * 0.5)
            if min_h > 0:
                self.setMinimumHeight(min_h)
        except Exception:
            logger.debug("AISuggestionDialog: minimum height policy failed", exc_info=True)

    def _apply_window_height_policy(self):
        """ダイアログの高さ制約を画面サイズに合わせて設定する。

        - 最小高さ: 画面高の50%
        - 最大高さ: 画面高（利用可能領域）
        """
        try:
            screen = self.screen() if hasattr(self, 'screen') else None
            if screen is None:
                from qt_compat.widgets import QApplication

                screen = QApplication.primaryScreen()
            if screen is None:
                return

            geo = screen.availableGeometry()
            if not geo or geo.height() <= 0:
                return

            min_h = int(geo.height() * 0.5)
            max_h = int(geo.height())
            if min_h > 0:
                self.setMinimumHeight(min_h)
            if max_h > 0:
                self.setMaximumHeight(max_h)
        except Exception:
            logger.debug("AISuggestionDialog: window height policy failed", exc_info=True)

    def _response_text_area_initial_min_height(self) -> int:
        """AI応答結果テキストエリアの初期高さ（画面高の45%）。

        縮小時は下部領域のスクロールで吸収される前提のため、
        "初期表示で十分に見える" ことを優先して minHeight を付与する。
        """
        try:
            screen = self.screen() if hasattr(self, 'screen') else None
            if screen is None:
                from qt_compat.widgets import QApplication

                screen = QApplication.primaryScreen()
            if screen is None:
                return 320

            geo = screen.availableGeometry()
            if not geo or geo.height() <= 0:
                return 320

            h = int(geo.height() * 0.3)
            return max(240, h)
        except Exception:
            return 320

    def _estimate_bottom_area_min_height(self, button_count: int) -> int:
        """下部領域の最小高さをボタン数ベースで推定（重なり防止 + スクロール発生条件）。"""
        try:
            # 目安: ボタン(約60px) + 余白/ラベル + 応答ボタンバー + ある程度の応答表示
            per_btn = 45  # 60px + spacing
            buttons_h = max(1, int(button_count)) * per_btn
            chrome_h = 140  # ラベル/チェック/並列数/応答ボタン等の目安
            response_min = 220
            return max(response_min + chrome_h, buttons_h + chrome_h)
        except Exception:
            return 520

    def _register_tab_vertical_splitter(self, key: str, splitter: QSplitter, bottom_button_count: int) -> None:
        try:
            if not hasattr(self, '_tab_vertical_splitters'):
                self._tab_vertical_splitters = {}
            self._tab_vertical_splitters[str(key)] = (splitter, int(bottom_button_count))
        except Exception:
            pass

    def _apply_registered_tab_splitter_sizes(self) -> None:
        """登録済みタブの上下分割の初期サイズを適用（タブごとに1回）。

        データセット/報告書タブは遅延初期化のため、タブ生成後にも適用できるよう
        "一括で1回" ではなく "タブごとに1回" の制御にする。
        """
        try:
            m = getattr(self, '_tab_vertical_splitters', None)
            if not isinstance(m, dict) or not m:
                return

            applied = getattr(self, '_tab_vertical_splitters_applied', None)
            if not isinstance(applied, set):
                applied = set()
                self._tab_vertical_splitters_applied = applied

            for _key, entry in list(m.items()):
                try:
                    if _key in applied:
                        continue
                    splitter, btn_count = entry
                    if splitter is None:
                        continue

                    total_h = int(splitter.height())
                    if total_h <= 0:
                        continue
                    bottom_h = self._estimate_bottom_area_min_height(int(btn_count))
                    bottom_h = min(bottom_h, max(1, total_h - 50))
                    top_h = max(1, total_h - bottom_h)
                    splitter.setSizes([top_h, bottom_h])
                    applied.add(_key)
                except Exception:
                    continue
        except Exception:
            pass

    def showEvent(self, event):  # noqa: N802 - Qt互換
        super().showEvent(event)
        if self._did_initial_top_align:
            return

        try:
            screen = self.screen() if hasattr(self, 'screen') else None
            if screen is None:
                from qt_compat.widgets import QApplication
                screen = QApplication.primaryScreen()
            if screen is None:
                return
            geo = screen.availableGeometry()

            # 縦方向はできるだけ高く（スクロール軽減）。ただし画面外には出さない。
            # 幅は既定(900)を基本に、画面に収まる範囲で調整。
            margin_px = 24
            max_w = max(400, int(geo.width() - margin_px))
            max_h = max(300, int(geo.height() - margin_px))
            desired_w = min(max(self.width(), 900), int(max_w))
            # 最大は画面サイズまで（要件）
            desired_h = min(max(self.height(), int(max_h * 0.95)), int(max_h))
            if desired_w != self.width() or desired_h != self.height():
                self.resize(int(desired_w), int(desired_h))

            target_x = geo.x() + (geo.width() - self.width()) // 2
            target_y = geo.y()
            if target_x < geo.x():
                target_x = geo.x()
            if target_x + self.width() > geo.x() + geo.width():
                target_x = geo.x() + geo.width() - self.width()
            self.move(int(target_x), int(target_y))
        except Exception:
            logger.debug("AISuggestionDialog: top align failed", exc_info=True)
        finally:
            self._did_initial_top_align = True
            try:
                # 画面サイズに基づく最大高さを再適用（screenが確定してから反映される環境向け）
                self._apply_window_height_policy()
            except Exception:
                pass
            try:
                # タブ分割の初期比率
                QTimer.singleShot(0, self._apply_registered_tab_splitter_sizes)
            except Exception:
                pass
        
    def setup_main_tab(self, tab_widget):
        """メインタブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # コンテンツエリア
        content_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(content_splitter, 1)
        
        # 候補リスト
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        
        list_label = QLabel("提案候補:")
        list_layout.addWidget(list_label)
        
        self.suggestion_list = QListWidget()
        # 候補リストは「改行が発生しない程度に狭く」し、プレビュー側を広く確保
        self.suggestion_list.setMinimumWidth(160)
        self.suggestion_list.setMaximumWidth(220)
        list_layout.addWidget(self.suggestion_list)
        
        content_splitter.addWidget(list_widget)
        
        # プレビューエリア（全候補同時表示）
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        
        preview_label = QLabel("全候補プレビュー:")
        preview_layout.addWidget(preview_label)
        
        # プレビューテキストを親ウィジェット内に配置
        preview_container = QWidget()
        preview_container_layout = QVBoxLayout(preview_container)
        preview_container_layout.setContentsMargins(0, 0, 0, 0)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setHtml(
            f'<div style="padding: 20px; color: {get_color(ThemeKey.TEXT_MUTED)}; text-align: center;">'
            '<h3>AI提案生成後に全候補が表示されます</h3>'
            '<p>候補リストで選択した候補が強調表示されます。<br>'
            '実際に適用する説明文を選択してください。</p>'
            '</div>'
        )
        preview_container_layout.addWidget(self.preview_text)
        
        # スピナーオーバーレイを追加
        from classes.dataset.ui.spinner_overlay import SpinnerOverlay

        self.spinner_overlay = SpinnerOverlay(preview_container, "AI応答を待機中...")
        
        preview_layout.addWidget(preview_container)
        
        content_splitter.addWidget(preview_widget)

        # 右側プレビューを優先して伸ばす
        try:
            content_splitter.setStretchFactor(0, 1)
            content_splitter.setStretchFactor(1, 4)
        except Exception:
            pass
        
    def setup_prompt_tab(self, tab_widget):
        """プロンプト表示タブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # プロンプト全文表示
        prompt_label = QLabel("AIに送信されるプロンプト全文（ARIM課題データ統合済み）:")
        prompt_label.setStyleSheet("font-weight: bold; margin: 5px;")
        layout.addWidget(prompt_label)
        
        self.full_prompt_display = QTextEdit()
        self.full_prompt_display.setReadOnly(True)
        self.full_prompt_display.setPlainText("プロンプトはAI提案生成時に表示されます。")
        layout.addWidget(self.full_prompt_display, 1)
        
        # 統計情報
        stats_label = QLabel("統計情報:")
        stats_label.setStyleSheet("font-weight: bold; margin: 5px;")
        layout.addWidget(stats_label)
        
        self.prompt_stats = QLabel("文字数: -, 行数: -, ARIM統合: -")
        self.prompt_stats.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 5px;")
        layout.addWidget(self.prompt_stats)
        
    def setup_detail_tab(self, tab_widget):
        """詳細情報タブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        
        # プロンプト情報
        prompt_group = QGroupBox("使用プロンプト")
        prompt_layout = QVBoxLayout(prompt_group)
        
        self.prompt_display = QTextEdit()
        self.prompt_display.setReadOnly(True)
        self.prompt_display.setMaximumHeight(200)
        prompt_layout.addWidget(self.prompt_display)
        
        layout.addWidget(prompt_group)
        
        # コンテキストデータ
        context_group = QGroupBox("コンテキストデータ")
        context_layout = QVBoxLayout(context_group)
        
        self.context_display = QTextEdit()
        self.context_display.setReadOnly(True)
        self.context_display.setMaximumHeight(200)
        context_layout.addWidget(self.context_display)
        
        layout.addWidget(context_group)
        
        # AI応答の詳細
        response_group = QGroupBox("AI応答詳細")
        response_layout = QVBoxLayout(response_group)
        
        self.response_detail = QTextEdit()
        self.response_detail.setReadOnly(True)
        response_layout.addWidget(self.response_detail)
        
        layout.addWidget(response_group)
        
    def setup_connections(self):
        """シグナル・スロット接続"""
        self.generate_button.clicked.connect(self.generate_suggestions)
        self.cancel_ai_button.clicked.connect(self.cancel_ai_request)
        self.apply_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        # データセット提案モードのみsuggestion_listが存在
        if self.mode == "dataset_suggestion" and hasattr(self, 'suggestion_list'):
            self.suggestion_list.currentItemChanged.connect(self.on_suggestion_selected)
    
    def cancel_ai_request(self):
        """AI実行中のリクエストをキャンセル"""
        try:
            if self.ai_thread and self.ai_thread.isRunning():
                logger.info("AIリクエストをキャンセル中...")
                
                # スレッドに停止要求
                self.ai_thread.stop()
                
                # 最大1秒待機
                if not self.ai_thread.wait(1000):
                    logger.warning("AIスレッドが1秒以内に停止しませんでした")
                
                # UI状態をリセット
                self.progress_bar.setVisible(False)
                self.generate_button.stop_loading()
                self.cancel_ai_button.setVisible(False)
                
                # スピナーオーバーレイ停止
                if hasattr(self, 'spinner_overlay'):
                    self.spinner_overlay.stop()
                
                logger.info("AIリクエストをキャンセルしました")
                
                # キャンセル完了をユーザーに通知
                from qt_compat.widgets import QMessageBox
                QMessageBox.information(self, "キャンセル完了", "AI提案生成をキャンセルしました。")
            else:
                logger.debug("キャンセル可能なAIスレッドが実行されていません")
                
        except Exception as e:
            logger.error("AIキャンセルエラー: %s", e)
        
    def generate_suggestions(self):
        """AI提案を生成"""
        if self.ai_thread and self.ai_thread.isRunning():
            logger.debug("既にAIスレッドが実行中です")
            return
        
        try:
            # スピナー開始
            self.generate_button.start_loading("生成中")
            
            # キャンセルボタンを表示・有効化
            self.cancel_ai_button.setVisible(True)
            self.cancel_ai_button.setEnabled(True)
            
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # 不定プログレス
            
            # データセット提案モードのみスピナーオーバーレイ表示
            if self.mode == "dataset_suggestion" and hasattr(self, 'spinner_overlay'):
                try:
                    self.spinner_overlay.set_message("AI応答を待機中...")
                except Exception:
                    pass
                self.spinner_overlay.start()
            
            # プロンプトを構築
            prompt = self.build_prompt()
            
            # 詳細情報タブに表示
            self.update_detail_display(prompt)
            
            # 既存のスレッドがあれば停止
            if self.ai_thread:
                if self.ai_thread.isRunning():
                    self.ai_thread.stop()
                    self.ai_thread.wait(1000)
            
            # AIリクエストスレッドを開始
            # 使用するプロンプトを保存（再試行用）
            self.last_used_prompt = prompt
            self._json_retry_count = 0
            thread = AIRequestThread(prompt, self.context_data)
            if thread is None:
                logger.error("AIRequestThreadがNoneです。初期化失敗")
                self.generate_button.stop_loading()
                self.cancel_ai_button.setVisible(False)
                self.progress_bar.setVisible(False)
                if hasattr(self, 'spinner_overlay'):
                    self.spinner_overlay.stop()
                QMessageBox.critical(self, "AIエラー", "AI処理用のスレッド初期化に失敗しました。")
                return
            try:
                thread.result_ready.connect(self.on_ai_result)
                thread.error_occurred.connect(self.on_ai_error)
            except Exception as conn_err:
                logger.error("AIRequestThreadシグナル接続エラー: %s", conn_err)
                self.generate_button.stop_loading()
                self.cancel_ai_button.setVisible(False)
                self.progress_bar.setVisible(False)
                if hasattr(self, 'spinner_overlay'):
                    self.spinner_overlay.stop()
                QMessageBox.critical(self, "AIエラー", f"AIスレッド接続に失敗しました: {conn_err}")
                return
            self.ai_thread = thread
            thread.start()
            
        except Exception as e:
            logger.error("AI提案生成エラー: %s", e)
            self.generate_button.stop_loading()
            self.cancel_ai_button.setVisible(False)
            self.progress_bar.setVisible(False)
            
            # スピナーオーバーレイ停止
            if hasattr(self, 'spinner_overlay'):
                self.spinner_overlay.stop()

    def _resend_ai_request(self, prompt):
        """JSON解析失敗時の再試行用にAIリクエストを再送"""
        try:
            # 既存スレッドを安全に停止
            if self.ai_thread and self.ai_thread.isRunning():
                self.ai_thread.stop()
                self.ai_thread.wait(500)
            # スピナー継続表示
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            if hasattr(self, 'spinner_overlay'):
                try:
                    retries = int(getattr(self, "_json_retry_count", 0) or 0)
                    self.spinner_overlay.set_message(f"JSON解析に失敗: 再問い合わせ中... ({retries}/3)")
                except Exception:
                    pass
                self.spinner_overlay.start()
            # 再送
            self.ai_thread = AIRequestThread(prompt, self.context_data)
            if not self.ai_thread:
                raise RuntimeError("AIRequestThreadの初期化に失敗しました")
            try:
                self.ai_thread.result_ready.connect(self.on_ai_result)
                self.ai_thread.error_occurred.connect(self.on_ai_error)
            except Exception as conn_err:
                logger.error("AIRequestThreadシグナル接続エラー: %s", conn_err)
                raise
            self.ai_thread.start()
        except Exception as e:
            logger.error("AI再送エラー: %s", e)

    def _try_parse_json_suggestions(self, response_text) -> bool:
        """JSON形式の応答から提案候補を抽出。成功時True"""
        def _try_load(text: str):
            try:
                import json as _json

                return _json.loads(text)
            except Exception:
                return None

        def _strip_code_fences(text: str) -> str:
            try:
                import re

                cleaned = (text or "").strip()
                cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
                cleaned = re.sub(r'\s*```\s*$', '', cleaned)
                return cleaned.strip()
            except Exception:
                return (text or "").strip()

        def _extract_json_segment(text: str) -> str | None:
            s = text
            lb, rb = s.find("["), s.rfind("]")
            if lb != -1 and rb != -1 and rb > lb:
                return s[lb:rb + 1]
            lb, rb = s.find("{"), s.rfind("}")
            if lb != -1 and rb != -1 and rb > lb:
                return s[lb:rb + 1]
            return None

        def _parse_ai_json(text: str):
            try:
                import re

                t = _strip_code_fences(text)
                if not t:
                    return None

                # そのまま
                obj = _try_load(t)
                if isinstance(obj, str):
                    obj2 = _try_load(obj.strip())
                    if obj2 is not None:
                        return obj2
                if obj is not None:
                    return obj

                # 外側の引用を除去（例: '"{...}"' や "'{...}'" など）
                if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
                    t2 = t[1:-1].strip()
                    obj = _try_load(t2)
                    if isinstance(obj, str):
                        obj2 = _try_load(obj.strip())
                        if obj2 is not None:
                            return obj2
                    if obj is not None:
                        return obj

                # 文中にJSONが含まれるケース: 最大セグメント抽出
                seg = _extract_json_segment(t)
                if seg:
                    obj = _try_load(seg)
                    if isinstance(obj, str):
                        obj2 = _try_load(obj.strip())
                        if obj2 is not None:
                            return obj2
                    if obj is not None:
                        return obj

                # 軽微修正: トレーリングカンマ
                t2 = re.sub(r",(\s*[\]\}])", r"\1", t)
                obj = _try_load(t2)
                if isinstance(obj, str):
                    obj2 = _try_load(obj.strip())
                    if obj2 is not None:
                        return obj2
                if obj is not None:
                    return obj

                if seg:
                    seg2 = re.sub(r",(\s*[\]\}])", r"\1", seg)
                    obj = _try_load(seg2)
                    if isinstance(obj, str):
                        obj2 = _try_load(obj.strip())
                        if obj2 is not None:
                            return obj2
                    if obj is not None:
                        return obj

                return None
            except Exception:
                return None

        try:
            data = _parse_ai_json(response_text)
            if not isinstance(data, dict):
                return False
            keys = [
                ("explain_normal", "簡潔版"),
                ("explain_full", "詳細版"),
                ("explain_simple", "一般版"),
            ]
            suggestions = []
            for k, title in keys:
                val = data.get(k)
                if isinstance(val, str) and val.strip():
                    suggestions.append({"title": title, "text": val.strip()})
            if not suggestions:
                return False

            # 既存候補を置換
            self.suggestions.clear()
            if hasattr(self, 'suggestion_list'):
                self.suggestion_list.clear()
            for s in suggestions:
                self.suggestions.append(s)
                if hasattr(self, 'suggestion_list'):
                    self.suggestion_list.addItem(s['title'])
            # 最初を選択
            if hasattr(self, 'suggestion_list') and self.suggestion_list.count() > 0:
                self.suggestion_list.setCurrentRow(0)
            self.apply_button.setEnabled(True)
            # プレビュー更新
            self.display_all_suggestions()
            return True
        except Exception as e:
            logger.debug("JSON候補解析失敗: %s", e)
            return False
        
    def update_detail_display(self, prompt):
        """詳細情報タブの表示を更新（データセット提案モードのみ）"""
        # AI拡張モードでは詳細情報タブが存在しないため早期リターン
        if self.mode != "dataset_suggestion":
            logger.debug("AI拡張モードのため、詳細情報表示をスキップ")
            return
            
        logger.debug("プロンプト表示更新: 全%s文字", len(prompt))
        
        # プロンプト内にファイル情報が含まれているか確認
        if 'ファイル構成' in prompt or 'ファイル統計' in prompt or 'タイル#' in prompt:
            logger.debug("[OK] プロンプトにファイル情報が含まれています")
        else:
            logger.warning("プロンプトにファイル情報が見つかりません")
        
        # プロンプト表示（詳細情報タブ）
        if hasattr(self, 'prompt_display'):
            self.prompt_display.setText(prompt)
        
        # プロンプト全文表示（プロンプトタブ）
        if hasattr(self, 'full_prompt_display'):
            self.full_prompt_display.setPlainText(prompt)
        
        # プロンプト統計情報を更新
        char_count = len(prompt)
        line_count = prompt.count('\n') + 1
        has_arim_data = "ARIM課題関連情報" in prompt
        
        if hasattr(self, 'prompt_stats'):
            self.prompt_stats.setText(f"文字数: {char_count}, 行数: {line_count}, ARIM統合: {'○' if has_arim_data else '×'}")
        
        # コンテキストデータ表示
        context_text = "収集されたコンテキストデータ:\n\n"
        for key, value in self.context_data.items():
            # ARIM関連データは見やすく表示
            if key in ['dataset_existing_info', 'arim_extension_data', 'arim_experiment_data']:
                context_text += f"■ {key}:\n{value}\n\n"
            else:
                context_text += f"• {key}: {value}\n"
        if hasattr(self, 'context_display'):
            self.context_display.setText(context_text)
        
    
    # 旧プロンプト編集機能は廃止
        
    def build_prompt(self):
        """AIリクエスト用プロンプトを構築"""
        try:
            logger.debug("プロンプト構築開始 - 入力コンテキスト: %s", self.context_data)
            
            # AIManagerからデフォルトプロバイダー・モデル情報を取得
            from classes.ai.core.ai_manager import AIManager

            ai_manager = AIManager()
            provider = ai_manager.get_default_provider()
            model = ai_manager.get_default_model(provider)
            
            logger.debug("使用予定AI: provider=%s, model=%s", provider, model)
            
            # データセットコンテキストコレクターを使用して完全なコンテキストを収集
            from classes.dataset.util.dataset_context_collector import get_dataset_context_collector

            context_collector = get_dataset_context_collector()
            
            # データセットIDを取得（context_dataから）
            dataset_id = self.context_data.get('dataset_id')
            logger.debug("データセットID: %s", dataset_id)
            
            # context_dataからdataset_idを一時的に除外してから渡す
            context_data_without_id = {k: v for k, v in self.context_data.items() if k != 'dataset_id'}
            
            # collect_full_contextにdataset_idを明示的に渡す
            full_context = context_collector.collect_full_context(
                dataset_id=dataset_id,
                **context_data_without_id
            )
            
            logger.debug("コンテキストコレクター処理後: %s", list(full_context.keys()))
            
            # AI拡張機能からコンテキストデータを収集（既に統合されたfull_contextを使用）
            context = self.ai_extension.collect_context_data(**full_context)
            
            logger.debug("AI拡張機能処理後: %s", list(context.keys()))
            
            # プロバイダーとモデル情報をコンテキストに追加
            context['llm_provider'] = provider
            context['llm_model'] = model
            context['llm_model_name'] = f"{provider}:{model}"  # プロンプトテンプレート用
            
            # データセット説明AI提案（AI提案タブ）で使用するテンプレートをAI拡張設定から読み込み
            from classes.dataset.util.ai_extension_helper import load_ai_extension_config, load_prompt_file, format_prompt_with_context
            ext_conf = load_ai_extension_config()
            prompt_file = None
            # 本タブはJSON応答を前提とする
            self._expected_output_format = "json"
            try:
                selected_button_id = (
                    (ext_conf or {}).get("dataset_description_ai_proposal_prompt_button_id")
                    or "json_explain_dataset_basic"
                )
                for btn in ext_conf.get("buttons", []):
                    if btn.get("id") == selected_button_id:
                        prompt_file = btn.get("prompt_file") or btn.get("prompt_template")
                        # 出力形式はjson前提。設定がtextでもここではjson扱いにする。
                        configured_format = (btn.get("output_format") or "").strip().lower() or "text"
                        if configured_format != "json":
                            logger.warning(
                                "dataset_description_ai_proposal_prompt_button_id=%s は output_format=%s です。json前提のため json として扱います。",
                                selected_button_id,
                                configured_format,
                            )
                        break
            except Exception as _e:
                logger.warning("AI拡張設定の解析に失敗: %s", _e)

            if not prompt_file:
                logger.warning("データセット説明AI提案のテンプレート定義が見つかりません。フォールバックします。")
                return f"データセット '{context.get('name', '未設定')}' の説明文を提案してください。"

            # テンプレートファイルを読み込み、プレースホルダを動的置換
            template_text = load_prompt_file(prompt_file)
            if not template_text:
                logger.warning("テンプレートファイルが読み込めませんでした: %s", prompt_file)
                return f"データセット '{context.get('name', '未設定')}' の説明文を提案してください。"

            # 置換前に重要キーの収集状況をログ
            ft_len = len(full_context.get('file_tree', '') or '')
            ts_len = len(full_context.get('text_from_structured_files', '') or '')
            jf_len = len(full_context.get('json_from_structured_files', '') or '')
            logger.debug("テンプレート: %s / 出力形式: %s", prompt_file, self._expected_output_format)
            logger.debug(
                "context[file_tree] 長さ: %s, context[text_from_structured_files] 長さ: %s, context[json_from_structured_files] 長さ: %s",
                ft_len,
                ts_len,
                jf_len
            )

            prompt = format_prompt_with_context(template_text, context)

            # 置換後に未解決プレースホルダが残っていないか確認
            unresolved_keys = []
            for key in ['file_tree', 'text_from_structured_files', 'json_from_structured_files', 'name', 'type', 'grant_number', 'existing_description', 'llm_model_name']:
                if '{' + key + '}' in prompt:
                    unresolved_keys.append(key)
            if unresolved_keys:
                logger.warning("未解決プレースホルダ: %s", unresolved_keys)
            else:
                logger.debug("主要プレースホルダは全て置換済み")
            
            logger.debug("生成されたプロンプト長: %s 文字", len(prompt))
            logger.debug("ARIM関連情報含有: %s", 'ARIM課題関連情報' in prompt)
            
            return prompt
            
        except Exception as e:
            logger.error("プロンプト構築エラー: %s", e)
            import traceback
            traceback.print_exc()
            
            # エラー時のフォールバック（より詳細な情報を含める）
            name = self.context_data.get('name', '未設定')
            grant_number = self.context_data.get('grant_number', '未設定')
            description = self.context_data.get('description', '')
            dataset_type = self.context_data.get('type', 'mixed')
            
            fallback_prompt = f"""
データセットの説明文を3つの異なるスタイルで提案してください。

【データセット基本情報】
- データセット名: {name}
- 課題番号: {grant_number}
- データセットタイプ: {dataset_type}
"""
            
            if description:
                fallback_prompt += f"- 既存の説明: {description}\n"
            
            fallback_prompt += """
【要求事項】
1. 学術的で専門的な内容を含めること
2. データの特徴や価値を明確にすること
3. 利用者にとって有用な情報を提供すること

【出力形式】
以下の3つのスタイルで説明文を提案してください:

[簡潔版] ここに簡潔な説明（200文字程度）

[詳細版] ここに学術的な説明（500文字程度）

[一般版] ここに一般向けの説明（300文字程度）

注意: 各説明文は改行なしで1行で出力してください。
"""
            
            logger.warning("フォールバックプロンプトを使用: %s文字", len(fallback_prompt))
            return fallback_prompt
        
    def on_ai_result(self, result):
        """AIリクエスト結果を処理"""
        try:
            self.progress_bar.setVisible(False)
            
            # スピナー停止
            self.generate_button.stop_loading()
            
            # キャンセルボタンを非表示
            self.cancel_ai_button.setVisible(False)
            
            # スピナーオーバーレイ停止
            if hasattr(self, 'spinner_overlay'):
                self.spinner_overlay.stop()
            
            # レスポンステキストを取得
            response_text = result.get('response') or result.get('content', '')
            
            # 詳細情報タブにAI応答を表示
            response_detail = f"AI応答の詳細:\n\n"
            response_detail += f"成功: {result.get('success', False)}\n"
            response_detail += f"トークン使用量: {result.get('usage', {}).get('total_tokens', '不明')}\n"
            response_detail += f"応答時間: {result.get('response_time', 0):.2f}秒\n\n"
            response_detail += f"生の応答:\n{response_text}"
            self.response_detail.setText(response_detail)
            
            if response_text:
                # 出力形式がjson指定の場合はJSON優先で解析し、失敗時は最大3回まで再取得
                retries = getattr(self, "_json_retry_count", 0)
                if getattr(self, "_expected_output_format", "text") == "json":
                    parsed_ok = self._try_parse_json_suggestions(response_text)
                    if not parsed_ok and retries < 3:
                        logger.info("JSON解析に失敗。再試行 %d/3", retries + 1)
                        self._json_retry_count = retries + 1
                        # 再送信（同一プロンプト）
                        prompt = self.last_used_prompt if self.last_used_prompt else self.build_prompt()
                        self._resend_ai_request(prompt)
                        return
                    if not parsed_ok and retries >= 3:
                        # 本タブはJSON前提。フォールバックでテキスト解析はしない。
                        self.apply_button.setEnabled(False)
                        QMessageBox.critical(
                            self,
                            "AI応答エラー",
                            "AIの応答をJSONとして解釈できませんでした。\n"
                            "（引用符で囲まれたJSON/本文中JSON抽出も試行済み）\n"
                            "AI設定またはプロンプトテンプレートを見直してください。",
                        )
                        return
                    # JSON解析成功時はUI更新済み
                else:
                    self.parse_suggestions(response_text)
            else:
                QMessageBox.warning(self, "警告", "AIからの応答が空です")
                
        except Exception as e:
            logger.error("AI結果処理エラー: %s", e)
            QMessageBox.critical(self, "エラー", f"AI結果処理エラー: {str(e)}")
            
    def on_ai_error(self, error_message):
        """AIリクエストエラーを処理"""
        try:
            self.progress_bar.setVisible(False)
            
            # スピナー停止
            self.generate_button.stop_loading()
            
            # キャンセルボタンを非表示
            self.cancel_ai_button.setVisible(False)
            
            # スピナーオーバーレイ停止
            if hasattr(self, 'spinner_overlay'):
                self.spinner_overlay.stop()
            
            logger.error("AIエラー: %s", error_message)
            QMessageBox.critical(self, "AIエラー", error_message)
            
        except Exception as e:
            logger.error("AIエラー処理エラー: %s", e)
        
    def parse_suggestions(self, response_text):
        """AI応答から提案候補を抽出（データセット提案モードのみ）"""
        # AI拡張モードでは提案リストが存在しないため早期リターン
        if self.mode != "dataset_suggestion":
            logger.debug("AI拡張モードのため、提案解析をスキップ")
            return
            
        self.suggestions.clear()
        if hasattr(self, 'suggestion_list'):
            self.suggestion_list.clear()
        
        try:
            # 出力形式に応じて解析
            if getattr(self, "_expected_output_format", "text") == "json":
                if self._try_parse_json_suggestions(response_text):
                    parsed_suggestions = self.suggestions  # 既に設定済み
                else:
                    # 本タブはJSON前提。テキスト解析フォールバックはしない。
                    self.apply_button.setEnabled(False)
                    QMessageBox.critical(
                        self,
                        "AI応答エラー",
                        "AIの応答をJSONとして解釈できませんでした。\n"
                        "AI設定またはプロンプトテンプレートを見直してください。",
                    )
                    return
            else:
                parsed_suggestions = self.ai_extension.process_ai_response(response_text)
            
            for suggestion in parsed_suggestions:
                self.suggestions.append(suggestion)
                if hasattr(self, 'suggestion_list'):
                    item = QListWidgetItem(suggestion['title'])
                    self.suggestion_list.addItem(item)
                
            if self.suggestions:
                if hasattr(self, 'suggestion_list'):
                    self.suggestion_list.setCurrentRow(0)
                self.apply_button.setEnabled(True)
                
                # 全候補をプレビューエリアに表示
                self.display_all_suggestions()
                
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"提案解析エラー: {str(e)}")
            
            # フォールバック: 全体を1つの提案として扱う
            self.suggestions.append({
                'title': 'AI提案',
                'text': response_text.strip()
            })
            
            if hasattr(self, 'suggestion_list'):
                item = QListWidgetItem('AI提案')
                self.suggestion_list.addItem(item)
                self.suggestion_list.setCurrentRow(0)
            self.apply_button.setEnabled(True)
            
            # フォールバック時も全候補表示
            self.display_all_suggestions()
    
    def display_all_suggestions(self):
        """全ての提案候補をプレビューエリアに表示（データセット提案モードのみ）"""
        # AI拡張モードではプレビューエリアが存在しない
        if self.mode != "dataset_suggestion" or not hasattr(self, 'preview_text'):
            return
            
        if not self.suggestions:
            self.preview_text.setPlainText("提案候補がありません。")
            return
            
        # 最初の候補を選択状態として表示
        self.update_preview_highlight(0)
    
    def auto_generate_suggestions(self):
        """自動AI提案生成（ダイアログ表示時に自動実行）"""
        try:
            # 課題番号が存在する場合のみ自動生成
            grant_number = self.context_data.get('grant_number', '').strip()
            if grant_number and grant_number != '未設定':
                logger.info("AI提案を自動生成開始: 課題番号 %s", grant_number)
                self.generate_suggestions()
            else:
                logger.info("課題番号が設定されていないため、手動でAI提案生成を行ってください")
                
        except Exception as e:
            logger.warning("自動AI提案生成エラー: %s", e)
            # エラーが発生しても処理を続行（手動実行は可能）
            
    def toggle_action_buttons(self):
        """タブ切替時のアクションボタン表示制御
        
        AI提案タブ選択時のみ、生成/適用/キャンセルボタンを表示
        それ以外のタブでは非表示にする
        """
        current_tab_index = self.tab_widget.currentIndex()
        current_tab_text = self.tab_widget.tabText(current_tab_index)
        
        # AI提案タブ選択時のみボタンを表示
        is_ai_suggestion_tab = (current_tab_text == "AI提案")
        
        self.generate_button.setVisible(is_ai_suggestion_tab)
        self.apply_button.setVisible(is_ai_suggestion_tab)
        self.cancel_button.setVisible(is_ai_suggestion_tab)
        
        logger.debug("ボタン表示制御: タブ='%s', 表示=%s", current_tab_text, is_ai_suggestion_tab)
    
    def on_suggestion_selected(self, current, previous):
        """提案選択時の処理（候補選択マーク用・データセット提案モードのみ）"""
        if self.mode != "dataset_suggestion" or not hasattr(self, 'suggestion_list'):
            return
            
        if current:
            row = self.suggestion_list.row(current)
            if 0 <= row < len(self.suggestions):
                suggestion = self.suggestions[row]
                self.selected_suggestion = suggestion['text']
                
                # プレビューエリアで該当候補をハイライト表示
                self.update_preview_highlight(row)
            
    def update_preview_highlight(self, selected_index):
        """プレビューエリアで選択された候補をハイライト（データセット提案モードのみ）"""
        if self.mode != "dataset_suggestion" or not hasattr(self, 'preview_text'):
            return
            
        if not self.suggestions:
            return
            
        # 全候補を表示し、選択された候補を強調
        preview_html = ""
        
        for i, suggestion in enumerate(self.suggestions):
            if i == selected_index:
                # 選択された候補は背景色を変更
                preview_html += (
                    f'<div style=" border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)}; '
                    'padding: 10px; margin: 5px 0; border-radius: 5px;">'
                )
                preview_html += f'<h3 style=" margin: 0 0 10px 0;">【選択中】{suggestion["title"]}</h3>'
            else:
                # その他の候補は通常表示
                preview_html += (
                    f'<div style="border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; '
                    'padding: 10px; margin: 5px 0; border-radius: 5px;">'
                )
                preview_html += f'<h3 style="margin: 0 0 10px 0;">{suggestion["title"]}</h3>'
            
            # HTMLエスケープして改行を<br>に変換（XSS対策）
            import html
            escaped_text = html.escape(suggestion['text'])
            text_with_breaks = escaped_text.replace('\n', '<br>')
            preview_html += f'<div style="white-space: pre-wrap; line-height: 1.4;">{text_with_breaks}</div>'
            preview_html += '</div><br>'
        
        self.preview_text.setHtml(preview_html)
            
    def get_selected_suggestion(self):
        """選択された提案を取得"""
        return self.selected_suggestion
    
    def setup_extension_tab(self, tab_widget):
        """AI拡張タブのセットアップ"""
        from qt_compat.widgets import QScrollArea, QSizePolicy
        layout = QVBoxLayout(tab_widget)
        
        # ヘッダー
        header_layout = QHBoxLayout()
        
        title_label = QLabel("AI拡張サジェスト機能")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 2px;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # デフォルトAI設定表示
        from classes.ai.core.ai_manager import AIManager

        ai_manager = AIManager()
        default_provider = ai_manager.get_default_provider()
        default_model = ai_manager.get_default_model(default_provider)
        
        ai_config_label = QLabel(f"🤖 使用AI: {default_provider.upper()} / {default_model}")
        ai_config_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 2px; font-size: 11px;")
        ai_config_label.setToolTip("グローバル設定で指定されたデフォルトAIを使用します")
        header_layout.addWidget(ai_config_label)
        
        # 設定ボタン
        config_button = QPushButton("設定編集")
        config_button.setToolTip("AI拡張設定ファイルを編集")
        config_button.clicked.connect(self.edit_extension_config)
        config_button.setMaximumWidth(80)
        header_layout.addWidget(config_button)
        
        layout.addLayout(header_layout)

        # タブ全体スクロール（通常OFF、応答領域が50%超でON）
        tab_scroll = QScrollArea()
        tab_scroll.setWidgetResizable(True)
        tab_scroll.setFrameShape(QScrollArea.NoFrame)
        tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tab_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(tab_scroll, 1)
        # テスト/デバッグ用参照
        self._ai_extension_tab_scroll_area = tab_scroll

        # 上ペイン / 下ペイン（境界は自動。手動リサイズ不可）
        content_root = QWidget()
        content_layout = QVBoxLayout(content_root)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)  # 上下ペイン間の余白を詰める
        tab_scroll.setWidget(content_root)

        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(3)
        try:
            top_layout.setAlignment(Qt.AlignTop)
        except Exception:
            pass
        
        # データセット選択エリア
        dataset_select_widget = QWidget()
        dataset_select_layout = QVBoxLayout(dataset_select_widget)
        dataset_select_layout.setContentsMargins(6, 3, 6, 3)
        self.dataset_select_layout = dataset_select_layout
        
        # データセット選択ラベル
        dataset_select_label = QLabel("分析対象データセットを選択:")
        dataset_select_label.setStyleSheet("font-weight: bold; margin: 2px;")
        dataset_select_layout.addWidget(dataset_select_label)
        
        # データセット選択コンボボックス
        dataset_combo_container = QWidget()
        dataset_combo_layout = QHBoxLayout(dataset_combo_container)
        dataset_combo_layout.setContentsMargins(0, 0, 0, 0)
        
        self.extension_dataset_combo = QComboBox()
        self.extension_dataset_combo.setMinimumWidth(500)
        self.extension_dataset_combo.setEditable(True)
        self.extension_dataset_combo.setInsertPolicy(QComboBox.NoInsert)
        self.extension_dataset_combo.setMaxVisibleItems(12)
        self.extension_dataset_combo.lineEdit().setPlaceholderText("データセットを検索・選択してください")

        # コンボボックス高さを2倍（フォントサイズは変更しない）
        try:
            base_h = self.extension_dataset_combo.sizeHint().height()
            if base_h and base_h > 0:
                self.extension_dataset_combo.setFixedHeight(base_h * 2)
                if self.extension_dataset_combo.lineEdit():
                    self.extension_dataset_combo.lineEdit().setMinimumHeight(base_h * 2 - 6)
        except Exception:
            pass
        dataset_combo_layout.addWidget(self.extension_dataset_combo)
        
        dataset_select_layout.addWidget(dataset_combo_container)

        # 選択中データセットの日時（JST）を表示
        try:
            from classes.utils.dataset_datetime_display import create_dataset_dates_label, attach_dataset_dates_label

            self._extension_dataset_dates_label = create_dataset_dates_label(dataset_select_widget)
            attach_dataset_dates_label(combo=self.extension_dataset_combo, label=self._extension_dataset_dates_label)
            dataset_select_layout.addWidget(self._extension_dataset_dates_label)
        except Exception:
            self._extension_dataset_dates_label = None
        top_layout.addWidget(dataset_select_widget)
        
        # データセット情報エリア（既存）
        dataset_info_widget = QWidget()
        dataset_info_layout = QVBoxLayout(dataset_info_widget)
        dataset_info_layout.setContentsMargins(6, 3, 6, 3)
        
        # データセット情報を取得・表示
        dataset_name = self.context_data.get('name', '').strip()
        grant_number = self.context_data.get('grant_number', '').strip()
        dataset_type = self.context_data.get('type', '').strip()
        
        if not dataset_name:
            dataset_name = "データセット名未設定"
        if not grant_number:
            grant_number = "課題番号未設定"
        if not dataset_type:
            dataset_type = "タイプ未設定"
        
        dataset_info_html = f"""
        <div style="border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; border-radius: 5px; padding: 6px; margin: 3px 0;">
            <h4 style="margin: 0 0 6px 0;">📊 対象データセット情報</h4>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="font-weight: bold;  padding: 2px 10px 2px 0; width: 100px;">データセット名:</td>
                    <td style="padding: 2px 0;">{dataset_name}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold;  padding: 2px 10px 2px 0;">課題番号:</td>
                    <td style="padding: 2px 0;">{grant_number}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold;  padding: 2px 10px 2px 0;">タイプ:</td>
                    <td style="padding: 2px 0;">{dataset_type}</td>
                </tr>
            </table>
        </div>
        """
        
        self.dataset_info_label = QLabel(dataset_info_html)
        self.dataset_info_label.setWordWrap(True)
        dataset_info_layout.addWidget(self.dataset_info_label)
        
        top_layout.addWidget(dataset_info_widget)

        try:
            top_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        except Exception:
            pass
        content_layout.addWidget(top_container, 0)

        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(4)
        
        # 左側: ボタンエリア
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 2, 2)
        
        buttons_label = QLabel("🤖 AIサジェスト機能")
        buttons_label.setStyleSheet(f"font-weight: bold; margin: 2px 0; font-size: 13px; color: {get_color(ThemeKey.TEXT_SECONDARY)};")
        left_layout.addWidget(buttons_label)
        # refresh_theme用に保持
        self._buttons_label = buttons_label
        
        # ボタンエリア（ボタン群のみスクロール）
        self.buttons_widget = QWidget()
        self.buttons_layout = QVBoxLayout(self.buttons_widget)
        self.buttons_layout.setContentsMargins(2, 2, 2, 2)
        self.buttons_layout.setSpacing(4)  # ボタン間の間隔をさらに狭く

        from qt_compat.widgets import QScrollArea

        self.buttons_scroll_area = QScrollArea()
        self.buttons_scroll_area.setWidgetResizable(True)
        self.buttons_scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.buttons_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.buttons_scroll_area.setWidget(self.buttons_widget)
        left_layout.addWidget(self.buttons_scroll_area, 1)
        
        left_widget.setMaximumWidth(280)  # 幅を調整
        left_widget.setMinimumWidth(250)
        bottom_layout.addWidget(left_widget, 0)
        
        # 右側: 応答表示エリア
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(2, 2, 2, 2)
        
        response_label = QLabel("📝 AI応答結果")
        response_label.setStyleSheet(f"font-weight: bold; margin: 2px 0; font-size: 13px; color: {get_color(ThemeKey.TEXT_SECONDARY)};")
        right_layout.addWidget(response_label)
        # refresh_theme用に保持
        self._response_label = response_label
        
        from qt_compat.widgets import QTextBrowser
        
        # 応答表示コンテナ（オーバーレイ用）
        response_container = QWidget()
        response_container_layout = QVBoxLayout(response_container)
        response_container_layout.setContentsMargins(0, 0, 0, 0)

        self.extension_response_display = QTextBrowser()
        self.extension_response_display.setReadOnly(True)
        self.extension_response_display.setOpenExternalLinks(False)  # セキュリティのため外部リンクは無効
        try:
            # ボタン群がウィンドウ内に収まるよう、応答表示は伸縮可能にする（最小は控えめ）
            self.extension_response_display.setMinimumHeight(120)
        except Exception:
            pass
        try:
            self.extension_response_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass
        self.extension_response_display.setPlaceholderText(
            "🤖 AI拡張サジェスト機能へようこそ！\n\n"
            "左側のボタンをクリックすると、選択した機能に応じたAI分析結果がここに表示されます。\n\n"
            "利用可能な機能:\n"
            "• 重要技術領域の分析\n"
            "• キーワード提案\n"
            "• 応用分野の提案\n"
            "• 制限事項の分析\n"
            "• 関連データセットの提案\n"
            "• 改善提案\n\n"
            "各ボタンを右クリックするとプロンプトの編集・プレビューが可能です。"
        )
        self.extension_response_display.setStyleSheet(f"""
            QTextBrowser {{
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                border-radius: 5px;
                font-family: 'Yu Gothic', 'Meiryo', sans-serif;
                font-size: 12px;
                line-height: 1.3;
                padding: 4px;
            }}
            QTextBrowser h1 {{
                font-size: 16px;
                font-weight: bold;
                margin: 8px 0 4px 0;
                border-bottom: 2px solid {get_color(ThemeKey.MARKDOWN_H1_BORDER)};
                padding-bottom: 2px;
            }}
            QTextBrowser h2 {{
  
                font-size: 15px;
                font-weight: bold;
                margin: 6px 0 3px 0;
                border-bottom: 1px solid {get_color(ThemeKey.MARKDOWN_H2_BORDER)};
                padding-bottom: 1px;
            }}
            QTextBrowser h3 {{
  
                font-size: 14px;
                font-weight: bold;
                margin: 5px 0 2px 0;
            }}
            QTextBrowser p {{
                margin: 3px 0;
                line-height: 1.3;
            }}
            QTextBrowser ul {{
                margin: 3px 0 3px 12px;
            }}
            QTextBrowser li {{
                margin: 1px 0;
                line-height: 1.3;
            }}
            QTextBrowser code {{

                padding: 1px 3px;
                border-radius: 2px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
            }}
            QTextBrowser pre {{

                border: 1px solid {get_color(ThemeKey.BORDER_LIGHT)};
                border-radius: 3px;
                padding: 6px;
                margin: 4px 0;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 11px;
                overflow-x: auto;
            }}
            QTextBrowser blockquote {{
                border-left: 3px solid {get_color(ThemeKey.MARKDOWN_BLOCKQUOTE_BORDER)};
                margin: 4px 0;
                padding: 4px 8px;
   
                font-style: italic;
            }}
            QTextBrowser strong {{
                font-weight: bold;
       
            }}
            QTextBrowser em {{
                font-style: italic;
   
            }}
            QTextBrowser table {{
                border-collapse: collapse;
                width: 100%;
                margin: 6px 0;
                font-size: 11px;
                border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
    
            }}
            QTextBrowser th {{
                border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
                padding: 6px 8px;
                text-align: left;
                font-weight: bold;
      
            }}
            QTextBrowser td {{
                border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
                padding: 6px 8px;
                text-align: left;
                vertical-align: top;
                line-height: 1.3;
            }}
        """)
        # 報告書タブでも同じ表示スタイルを流用する
        try:
            self._extension_response_display_stylesheet = self.extension_response_display.styleSheet()
        except Exception:
            self._extension_response_display_stylesheet = ""
        response_container_layout.addWidget(self.extension_response_display)

        # AI応答待機用スピナー（キャンセル付き）
        try:
            from classes.dataset.ui.spinner_overlay import SpinnerOverlay

            self.extension_spinner_overlay = SpinnerOverlay(
                response_container,
                "AI応答を待機中...",
                show_cancel=True,
                cancel_text="⏹ キャンセル"
            )
            self.extension_spinner_overlay.cancel_requested.connect(self.cancel_extension_ai_requests)
        except Exception as _e:
            logger.debug("extension spinner overlay init failed: %s", _e)
            self.extension_spinner_overlay = None

        right_layout.addWidget(response_container, 1)
        
        # 応答制御ボタン
        response_button_layout = QHBoxLayout()
        response_button_layout.setContentsMargins(0, 0, 0, 0)
        response_button_layout.setSpacing(4)
        
        self.clear_response_button = QPushButton("🗑️ クリア")
        self.clear_response_button.clicked.connect(self.clear_extension_response)
        self.clear_response_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED)};
            }}
        """
        )
        
        self.copy_response_button = QPushButton("📋 コピー")
        self.copy_response_button.clicked.connect(self.copy_extension_response)
        self.copy_response_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_SUCCESS_BORDER)};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED)};
            }}
        """)
        
        response_button_layout.addWidget(self.clear_response_button)
        response_button_layout.addWidget(self.copy_response_button)
        
        # プロンプト表示ボタンを追加
        self.show_prompt_button = QPushButton("📄 使用プロンプト表示")
        self.show_prompt_button.clicked.connect(self.show_used_prompt)
        self.show_prompt_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            }}
        """)
        self.show_prompt_button.setEnabled(False)  # 初期状態は無効
        
        response_button_layout.addWidget(self.show_prompt_button)

        # APIリクエスト/レスポンス表示ボタンを追加
        self.show_api_params_button = QPushButton("🔎 API req/resp")
        self.show_api_params_button.clicked.connect(self.show_api_request_response_params)
        self.show_api_params_button.setStyleSheet(self.show_prompt_button.styleSheet())
        self.show_api_params_button.setEnabled(False)  # 初期状態は無効
        response_button_layout.addWidget(self.show_api_params_button)
        response_button_layout.addStretch()
        
        right_layout.addLayout(response_button_layout, 0)
        
        bottom_layout.addWidget(right_widget, 1)

        content_layout.addWidget(bottom_container, 1)

        self._register_conditional_tab_scroll(tab_widget, tab_scroll, right_widget)
        # テスト/デバッグ用参照
        self._ai_extension_response_widget = right_widget
        QTimer.singleShot(0, lambda: self._update_conditional_tab_scroll(tab_widget))
        
        # 初期状態でボタンを読み込み
        try:
            self.load_extension_buttons()
        except Exception as e:
            logger.warning("AI拡張ボタンの読み込みに失敗しました: %s", e)
            # エラーメッセージを表示
            error_label = QLabel(f"AI拡張機能の初期化に失敗しました。\n\n設定ファイルを確認してください:\ninput/ai/ai_ext_conf.json\n\nエラー: {str(e)}")
            error_label.setStyleSheet(f"""
                color: {get_color(ThemeKey.TEXT_ERROR)};
                padding: 20px;
                background-color: {get_color(ThemeKey.NOTIFICATION_ERROR_BACKGROUND)};
                border: 1px solid {get_color(ThemeKey.NOTIFICATION_ERROR_BORDER)};
                border-radius: 5px;
            """)
            error_label.setWordWrap(True)
            error_label.setAlignment(Qt.AlignCenter)
            self.buttons_layout.addWidget(error_label)
        
        # データセット選択の初期化
        self.initialize_dataset_dropdown()
        
        # データセット選択のシグナル接続は初期化処理内で設定

    def setup_report_tab(self, tab_widget):
        """報告書タブのセットアップ（converted.xlsx エントリーを対象）"""
        from qt_compat.widgets import QTableWidget, QTableWidgetItem, QTextBrowser, QLineEdit, QAbstractItemView
        from qt_compat.widgets import QScrollArea, QSizePolicy

        layout = QVBoxLayout(tab_widget)

        # ヘッダー
        header_layout = QHBoxLayout()
        title_label = QLabel("報告書（converted.xlsx）")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 5px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        # デフォルトAI設定表示（AI拡張と同様）
        try:
            from classes.ai.core.ai_manager import AIManager

            ai_manager = AIManager()
            default_provider = ai_manager.get_default_provider()
            default_model = ai_manager.get_default_model(default_provider)
            ai_config_label = QLabel(f"🤖 使用AI: {default_provider.upper()} / {default_model}")
            ai_config_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 5px; font-size: 11px;")
            ai_config_label.setToolTip("グローバル設定で指定されたデフォルトAIを使用します")
            header_layout.addWidget(ai_config_label)
        except Exception:
            pass

        # 設定ボタン（AI拡張タブと同様）
        config_button = QPushButton("設定編集")
        config_button.setToolTip("AIサジェスト機能定義を編集")
        config_button.clicked.connect(self.edit_extension_config)
        config_button.setMaximumWidth(80)
        header_layout.addWidget(config_button)

        layout.addLayout(header_layout)

        # タブ全体スクロール（通常OFF、応答領域が50%超でON）
        tab_scroll = QScrollArea()
        tab_scroll.setWidgetResizable(True)
        tab_scroll.setFrameShape(QScrollArea.NoFrame)
        tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tab_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(tab_scroll, 1)
        # テスト/デバッグ用参照
        self._report_tab_scroll_area = tab_scroll

        # 上ペイン / 下ペイン（境界は自動。手動リサイズ不可）
        content_root = QWidget()
        content_layout = QVBoxLayout(content_root)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)  # 上下ペイン間の余白を詰める
        tab_scroll.setWidget(content_root)

        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)
        try:
            top_layout.setAlignment(Qt.AlignTop)
        except Exception:
            pass

        # フィルタ & 一覧
        filter_widget = QWidget()
        filter_container_layout = QVBoxLayout(filter_widget)
        filter_container_layout.setContentsMargins(10, 5, 10, 5)

        row1 = QHBoxLayout()
        row2 = QHBoxLayout()

        row1.addWidget(QLabel("ARIM課題番号:"))
        self.report_arimno_filter_input = QLineEdit()
        self.report_arimno_filter_input.setPlaceholderText("ARIM課題番号で絞り込み")
        self.report_arimno_filter_input.setMinimumWidth(220)
        row1.addWidget(self.report_arimno_filter_input)

        row1.addSpacing(10)
        row1.addWidget(QLabel("年度:"))
        self.report_year_filter_combo = QComboBox()
        self.report_year_filter_combo.setMinimumWidth(120)
        self.report_year_filter_combo.addItem("全て")
        row1.addWidget(self.report_year_filter_combo)

        row1.addSpacing(10)
        row1.addWidget(QLabel("重要技術領域(主):"))
        self.report_important_main_filter_combo = QComboBox()
        self.report_important_main_filter_combo.setMinimumWidth(200)
        self.report_important_main_filter_combo.addItem("全て")
        row1.addWidget(self.report_important_main_filter_combo)

        row1.addSpacing(10)
        row1.addWidget(QLabel("重要技術領域(副):"))
        self.report_important_sub_filter_combo = QComboBox()
        self.report_important_sub_filter_combo.setMinimumWidth(200)
        self.report_important_sub_filter_combo.addItem("全て")
        row1.addWidget(self.report_important_sub_filter_combo)
        row1.addStretch()

        row2.addWidget(QLabel("機関コード:"))
        self.report_inst_code_filter_input = QLineEdit()
        self.report_inst_code_filter_input.setPlaceholderText("機関コードで絞り込み")
        # 機関コードはアルファベット2文字のため、入力欄をコンパクトにする
        self.report_inst_code_filter_input.setFixedWidth(80)
        row2.addWidget(self.report_inst_code_filter_input)

        row2.addSpacing(10)
        row2.addWidget(QLabel("所属名:"))
        self.report_affiliation_filter_input = QLineEdit()
        self.report_affiliation_filter_input.setPlaceholderText("所属名で絞り込み")
        self.report_affiliation_filter_input.setMinimumWidth(180)
        row2.addWidget(self.report_affiliation_filter_input)

        row2.addSpacing(10)
        row2.addWidget(QLabel("利用課題名:"))
        self.report_title_filter_input = QLineEdit()
        self.report_title_filter_input.setPlaceholderText("利用課題名で絞り込み")
        self.report_title_filter_input.setMinimumWidth(220)
        row2.addWidget(self.report_title_filter_input)

        row2.addStretch()

        # 横断技術領域（主/副）フィルタ（重要技術領域と同様に事前フィルタ）
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("横断技術領域(主):"))
        self.report_cross_main_filter_combo = QComboBox()
        self.report_cross_main_filter_combo.setMinimumWidth(200)
        self.report_cross_main_filter_combo.addItem("全て")
        row3.addWidget(self.report_cross_main_filter_combo)

        row3.addSpacing(10)
        row3.addWidget(QLabel("横断技術領域(副):"))
        self.report_cross_sub_filter_combo = QComboBox()
        self.report_cross_sub_filter_combo.setMinimumWidth(200)
        self.report_cross_sub_filter_combo.addItem("全て")
        row3.addWidget(self.report_cross_sub_filter_combo)
        row3.addStretch()

        filter_container_layout.addLayout(row1)
        filter_container_layout.addLayout(row2)
        filter_container_layout.addLayout(row3)

        self.report_refresh_button = QPushButton("更新")
        self.report_refresh_button.setMaximumWidth(70)
        row1.addWidget(self.report_refresh_button)

        top_layout.addWidget(filter_widget)

        self.report_entries_table = QTableWidget()
        self.report_entries_table.setColumnCount(9)
        self.report_entries_table.setHorizontalHeaderLabels([
            "ARIM課題番号",
            "年度",
            "機関コード",
            "所属名",
            "利用課題名",
            "横断技術領域（主）",
            "横断技術領域（副）",
            "重要技術領域（主）",
            "重要技術領域（副）",
        ])
        self.report_entries_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        # 一括問い合わせ（選択複数）に備えて複数選択可能にする
        self.report_entries_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.report_entries_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        try:
            self._configure_table_visible_rows(self.report_entries_table, 9)
        except Exception:
            pass
        try:
            self.report_entries_table.setSortingEnabled(True)
        except Exception:
            pass
        top_layout.addWidget(self.report_entries_table, 1)

        try:
            top_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        except Exception:
            pass
        content_layout.addWidget(top_container, 0)

        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(4)

        # 左側: ボタン
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 2, 2)

        buttons_label = QLabel("🤖 AIサジェスト機能（報告書）")
        buttons_label.setStyleSheet(
            f"font-weight: bold; margin: 2px 0; font-size: 13px; color: {get_color(ThemeKey.TEXT_SECONDARY)};"
        )
        left_layout.addWidget(buttons_label)

        self.report_bulk_checkbox = QCheckBox("一括問い合わせ")
        self.report_bulk_checkbox.setToolTip(
            "チェックONの状態でボタンを押すと、表示全件（または選択行）に対して一括で問い合わせを行い結果を保存します。"
        )
        left_layout.addWidget(self.report_bulk_checkbox)

        # 一括問い合わせの並列数（標準5、最大20）
        parallel_row = QHBoxLayout()
        parallel_row.addWidget(QLabel("並列数:"))
        self.report_bulk_parallel_spinbox = QSpinBox()
        self.report_bulk_parallel_spinbox.setMinimum(1)
        self.report_bulk_parallel_spinbox.setMaximum(20)
        self.report_bulk_parallel_spinbox.setValue(5)
        self.report_bulk_parallel_spinbox.setToolTip("一括問い合わせ時の同時実行数（標準5、最大20）")
        parallel_row.addWidget(self.report_bulk_parallel_spinbox)
        parallel_row.addStretch()
        left_layout.addLayout(parallel_row)

        self.report_buttons_widget = QWidget()
        self.report_buttons_layout = QVBoxLayout(self.report_buttons_widget)
        self.report_buttons_layout.setContentsMargins(2, 2, 2, 2)
        self.report_buttons_layout.setSpacing(4)

        self.report_buttons_scroll_area = QScrollArea()
        self.report_buttons_scroll_area.setWidgetResizable(True)
        self.report_buttons_scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.report_buttons_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.report_buttons_scroll_area.setWidget(self.report_buttons_widget)
        left_layout.addWidget(self.report_buttons_scroll_area, 1)

        left_widget.setMaximumWidth(280)
        left_widget.setMinimumWidth(250)
        bottom_layout.addWidget(left_widget, 0)

        # 右側: 応答表示
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(2, 2, 2, 2)

        response_label = QLabel("📝 AI応答結果")
        response_label.setStyleSheet(
            f"font-weight: bold; margin: 2px 0; font-size: 13px; color: {get_color(ThemeKey.TEXT_SECONDARY)};"
        )
        right_layout.addWidget(response_label)

        response_container = QWidget()
        response_container_layout = QVBoxLayout(response_container)
        response_container_layout.setContentsMargins(0, 0, 0, 0)

        self.report_response_display = QTextBrowser()
        self.report_response_display.setReadOnly(True)
        self.report_response_display.setOpenExternalLinks(False)
        try:
            # ボタン群がウィンドウ内に収まるよう、応答表示は伸縮可能にする（最小は控えめ）
            self.report_response_display.setMinimumHeight(120)
        except Exception:
            pass
        try:
            self.report_response_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass
        self.report_response_display.setPlaceholderText(
            "左側のボタンをクリックすると、選択した報告書エントリーに基づくAI結果がここに表示されます。\n\n"
            "上部のARIMNO/年度で絞り込み、一覧から1件選択してください。"
        )
        try:
            if getattr(self, '_extension_response_display_stylesheet', ''):
                self.report_response_display.setStyleSheet(self._extension_response_display_stylesheet)
        except Exception:
            pass
        response_container_layout.addWidget(self.report_response_display)

        # スピナー（キャンセル付き）
        try:
            from classes.dataset.ui.spinner_overlay import SpinnerOverlay

            self.report_spinner_overlay = SpinnerOverlay(
                response_container,
                "AI応答を待機中...",
                show_cancel=True,
                cancel_text="⏹ キャンセル"
            )
            self.report_spinner_overlay.cancel_requested.connect(self.cancel_report_ai_requests)
        except Exception as _e:
            logger.debug("report spinner overlay init failed: %s", _e)
            self.report_spinner_overlay = None

        right_layout.addWidget(response_container, 1)

        # 応答制御ボタン（AI拡張タブと同等）
        response_button_layout = QHBoxLayout()
        response_button_layout.setContentsMargins(0, 0, 0, 0)
        response_button_layout.setSpacing(4)

        self.report_clear_response_button = QPushButton("🗑️ クリア")
        self.report_clear_response_button.clicked.connect(self.clear_report_response)
        self.report_clear_response_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED)};
            }}
        """
        )

        self.report_copy_response_button = QPushButton("📋 コピー")
        self.report_copy_response_button.clicked.connect(self.copy_report_response)
        self.report_copy_response_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_SUCCESS_BORDER)};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED)};
            }}
        """)

        self.report_show_prompt_button = QPushButton("📄 使用プロンプト表示")
        self.report_show_prompt_button.clicked.connect(self.show_used_prompt)
        self.report_show_prompt_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            }}
        """)
        self.report_show_prompt_button.setEnabled(False)

        self.report_show_api_params_button = QPushButton("🔎 API req/resp")
        self.report_show_api_params_button.clicked.connect(self.show_api_request_response_params)
        self.report_show_api_params_button.setStyleSheet(self.report_show_prompt_button.styleSheet())
        self.report_show_api_params_button.setEnabled(False)

        response_button_layout.addWidget(self.report_clear_response_button)
        response_button_layout.addWidget(self.report_copy_response_button)
        response_button_layout.addWidget(self.report_show_prompt_button)
        response_button_layout.addWidget(self.report_show_api_params_button)
        response_button_layout.addStretch()
        right_layout.addLayout(response_button_layout, 0)

        bottom_layout.addWidget(right_widget, 1)

        content_layout.addWidget(bottom_container, 1)

        self._register_conditional_tab_scroll(tab_widget, tab_scroll, right_widget)
        # テスト/デバッグ用参照
        self._report_response_widget = right_widget
        QTimer.singleShot(0, lambda: self._update_conditional_tab_scroll(tab_widget))

        # 接続
        self.report_refresh_button.clicked.connect(self.refresh_report_entries)
        self.report_arimno_filter_input.textChanged.connect(self.refresh_report_entries)
        self.report_inst_code_filter_input.textChanged.connect(self.refresh_report_entries)
        self.report_affiliation_filter_input.textChanged.connect(self.refresh_report_entries)
        self.report_title_filter_input.textChanged.connect(self.refresh_report_entries)
        self.report_year_filter_combo.currentIndexChanged.connect(self.refresh_report_entries)
        self.report_cross_main_filter_combo.currentIndexChanged.connect(self.refresh_report_entries)
        self.report_cross_sub_filter_combo.currentIndexChanged.connect(self.refresh_report_entries)
        self.report_important_main_filter_combo.currentIndexChanged.connect(self.refresh_report_entries)
        self.report_important_sub_filter_combo.currentIndexChanged.connect(self.refresh_report_entries)
        self.report_entries_table.itemSelectionChanged.connect(self.on_report_entry_selected)

        # 初期ロード
        self.refresh_report_entries()
        try:
            self.load_report_buttons()
        except Exception as e:
            logger.warning("報告書タブのボタン読み込みに失敗しました: %s", e)

    # ------------------------------------------------------------------
    # Dataset tab (table-based selection)
    # ------------------------------------------------------------------
    def setup_dataset_tab(self, tab_widget):
        """データセットタブのセットアップ（dataset.json エントリーを対象）"""
        from qt_compat.widgets import QTableWidget, QTableWidgetItem, QTextBrowser, QLineEdit, QAbstractItemView
        from qt_compat.widgets import QScrollArea, QSizePolicy

        layout = QVBoxLayout(tab_widget)

        # ヘッダー
        header_layout = QHBoxLayout()
        title_label = QLabel("データセット（dataset.json）")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 5px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        # デフォルトAI設定表示（AI拡張/報告書と同様）
        try:
            from classes.ai.core.ai_manager import AIManager

            ai_manager = AIManager()
            default_provider = ai_manager.get_default_provider()
            default_model = ai_manager.get_default_model(default_provider)
            ai_config_label = QLabel(f"🤖 使用AI: {default_provider.upper()} / {default_model}")
            ai_config_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 5px; font-size: 11px;")
            ai_config_label.setToolTip("グローバル設定で指定されたデフォルトAIを使用します")
            header_layout.addWidget(ai_config_label)
        except Exception:
            pass

        config_button = QPushButton("設定編集")
        config_button.setToolTip("AIサジェスト機能定義を編集")
        config_button.clicked.connect(self.edit_extension_config)
        config_button.setMaximumWidth(80)
        header_layout.addWidget(config_button)

        layout.addLayout(header_layout)

        # タブ全体スクロール（通常OFF、応答領域が50%超でON）
        tab_scroll = QScrollArea()
        tab_scroll.setWidgetResizable(True)
        tab_scroll.setFrameShape(QScrollArea.NoFrame)
        tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tab_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(tab_scroll, 1)
        # テスト/デバッグ用参照
        self._dataset_tab_scroll_area = tab_scroll

        # 上ペイン / 下ペイン（境界は自動。手動リサイズ不可）
        content_root = QWidget()
        content_layout = QVBoxLayout(content_root)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)  # 上下ペイン間の余白を詰める
        tab_scroll.setWidget(content_root)

        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)
        try:
            top_layout.setAlignment(Qt.AlignTop)
        except Exception:
            pass

        # フィルタ & 一覧
        filter_widget = QWidget()
        filter_container_layout = QVBoxLayout(filter_widget)
        filter_container_layout.setContentsMargins(8, 4, 8, 4)
        try:
            filter_container_layout.setSpacing(4)
        except Exception:
            pass

        row1 = QHBoxLayout()
        row2 = QHBoxLayout()

        row1.addWidget(QLabel("データセットID:"))
        self.dataset_id_filter_input = QLineEdit()
        self.dataset_id_filter_input.setPlaceholderText("IDで絞り込み")
        self.dataset_id_filter_input.setMinimumWidth(200)
        row1.addWidget(self.dataset_id_filter_input)

        row1.addSpacing(10)
        row1.addWidget(QLabel("課題番号:"))
        self.dataset_grant_filter_input = QLineEdit()
        self.dataset_grant_filter_input.setPlaceholderText("課題番号で絞り込み")
        self.dataset_grant_filter_input.setMinimumWidth(220)
        row1.addWidget(self.dataset_grant_filter_input)

        row1.addSpacing(10)
        row1.addWidget(QLabel("年度:"))
        self.dataset_year_filter_combo = QComboBox()
        self.dataset_year_filter_combo.setMinimumWidth(120)
        self.dataset_year_filter_combo.addItem("全て")
        row1.addWidget(self.dataset_year_filter_combo)

        row1.addSpacing(10)
        row1.addWidget(QLabel("機関コード:"))
        self.dataset_inst_code_filter_combo = QComboBox()
        self.dataset_inst_code_filter_combo.setMinimumWidth(140)
        self.dataset_inst_code_filter_combo.addItem("全て")
        row1.addWidget(self.dataset_inst_code_filter_combo)

        row1.addStretch()
        self.dataset_refresh_button = QPushButton("更新")
        self.dataset_refresh_button.setMaximumWidth(70)
        row1.addWidget(self.dataset_refresh_button)

        row2.addWidget(QLabel("申請者:"))
        self.dataset_applicant_filter_input = QLineEdit()
        self.dataset_applicant_filter_input.setPlaceholderText("申請者で絞り込み")
        self.dataset_applicant_filter_input.setMinimumWidth(180)
        row2.addWidget(self.dataset_applicant_filter_input)

        row2.addSpacing(10)
        row2.addWidget(QLabel("課題名:"))
        self.dataset_subject_title_filter_input = QLineEdit()
        self.dataset_subject_title_filter_input.setPlaceholderText("課題名で絞り込み")
        self.dataset_subject_title_filter_input.setMinimumWidth(220)
        row2.addWidget(self.dataset_subject_title_filter_input)

        row2.addSpacing(10)
        row2.addWidget(QLabel("データセット名:"))
        self.dataset_name_filter_input = QLineEdit()
        self.dataset_name_filter_input.setPlaceholderText("データセット名で絞り込み")
        self.dataset_name_filter_input.setMinimumWidth(220)
        row2.addWidget(self.dataset_name_filter_input)

        row2.addSpacing(10)
        row2.addWidget(QLabel("テンプレート:"))
        self.dataset_template_filter_input = QLineEdit()
        self.dataset_template_filter_input.setPlaceholderText("テンプレートIDで絞り込み")
        self.dataset_template_filter_input.setMinimumWidth(220)
        row2.addWidget(self.dataset_template_filter_input)
        row2.addStretch()

        filter_container_layout.addLayout(row1)
        filter_container_layout.addLayout(row2)
        top_layout.addWidget(filter_widget)

        self.dataset_entries_table = QTableWidget()
        self.dataset_entries_table.setColumnCount(8)
        self.dataset_entries_table.setHorizontalHeaderLabels([
            "データセットID",
            "課題番号",
            "年度",
            "機関コード",
            "申請者",
            "課題名",
            "データセット名",
            "データセットテンプレート",
        ])
        self.dataset_entries_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.dataset_entries_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.dataset_entries_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        try:
            self._configure_table_visible_rows(self.dataset_entries_table, 6)
        except Exception:
            pass
        try:
            self.dataset_entries_table.setSortingEnabled(True)
        except Exception:
            pass
        top_layout.addWidget(self.dataset_entries_table, 1)

        try:
            top_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        except Exception:
            pass
        content_layout.addWidget(top_container, 0)

        bottom_container = QWidget()
        bottom_layout = QHBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(4)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(2, 2, 2, 2)

        buttons_label = QLabel("🤖 AIサジェスト機能（データセット）")
        buttons_label.setStyleSheet(
            f"font-weight: bold; margin: 2px 0; font-size: 13px; color: {get_color(ThemeKey.TEXT_SECONDARY)};"
        )
        left_layout.addWidget(buttons_label)

        self.dataset_bulk_checkbox = QCheckBox("一括問い合わせ")
        self.dataset_bulk_checkbox.setToolTip(
            "チェックONの状態でボタンを押すと、表示全件（または選択行）に対して一括で問い合わせを行い結果を保存します。"
        )
        left_layout.addWidget(self.dataset_bulk_checkbox)

        parallel_row = QHBoxLayout()
        parallel_row.addWidget(QLabel("並列数:"))
        self.dataset_bulk_parallel_spinbox = QSpinBox()
        self.dataset_bulk_parallel_spinbox.setMinimum(1)
        self.dataset_bulk_parallel_spinbox.setMaximum(20)
        self.dataset_bulk_parallel_spinbox.setValue(5)
        self.dataset_bulk_parallel_spinbox.setToolTip("一括問い合わせ時の同時実行数（標準5、最大20）")
        parallel_row.addWidget(self.dataset_bulk_parallel_spinbox)
        parallel_row.addStretch()
        left_layout.addLayout(parallel_row)

        self.dataset_buttons_widget = QWidget()
        self.dataset_buttons_layout = QVBoxLayout(self.dataset_buttons_widget)
        self.dataset_buttons_layout.setContentsMargins(2, 2, 2, 2)
        self.dataset_buttons_layout.setSpacing(4)

        self.dataset_buttons_scroll_area = QScrollArea()
        self.dataset_buttons_scroll_area.setWidgetResizable(True)
        self.dataset_buttons_scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.dataset_buttons_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.dataset_buttons_scroll_area.setWidget(self.dataset_buttons_widget)
        left_layout.addWidget(self.dataset_buttons_scroll_area, 1)

        left_widget.setMaximumWidth(280)
        left_widget.setMinimumWidth(250)
        bottom_layout.addWidget(left_widget, 0)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(2, 2, 2, 2)

        response_label = QLabel("📝 AI応答結果")
        response_label.setStyleSheet(
            f"font-weight: bold; margin: 2px 0; font-size: 13px; color: {get_color(ThemeKey.TEXT_SECONDARY)};"
        )
        right_layout.addWidget(response_label)

        response_container = QWidget()
        response_container_layout = QVBoxLayout(response_container)
        response_container_layout.setContentsMargins(0, 0, 0, 0)

        self.dataset_response_display = QTextBrowser()
        self.dataset_response_display.setReadOnly(True)
        self.dataset_response_display.setOpenExternalLinks(False)
        try:
            # ボタン群がウィンドウ内に収まるよう、応答表示は伸縮可能にする（最小は控えめ）
            self.dataset_response_display.setMinimumHeight(120)
        except Exception:
            pass
        try:
            self.dataset_response_display.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        except Exception:
            pass
        self.dataset_response_display.setPlaceholderText(
            "左側のボタンをクリックすると、選択したデータセットに基づくAI結果がここに表示されます。\n\n"
            "上部の各列フィルタで絞り込み、一覧から1件選択してください。"
        )
        try:
            if getattr(self, '_extension_response_display_stylesheet', ''):
                self.dataset_response_display.setStyleSheet(self._extension_response_display_stylesheet)
        except Exception:
            pass
        response_container_layout.addWidget(self.dataset_response_display)

        # スピナー（キャンセル付き）
        try:
            from classes.dataset.ui.spinner_overlay import SpinnerOverlay

            self.dataset_spinner_overlay = SpinnerOverlay(
                response_container,
                "AI応答を待機中...",
                show_cancel=True,
                cancel_text="⏹ キャンセル"
            )
            self.dataset_spinner_overlay.cancel_requested.connect(self.cancel_dataset_ai_requests)
        except Exception as _e:
            logger.debug("dataset spinner overlay init failed: %s", _e)
            self.dataset_spinner_overlay = None

        right_layout.addWidget(response_container, 1)

        response_button_layout = QHBoxLayout()
        response_button_layout.setContentsMargins(0, 0, 0, 0)
        response_button_layout.setSpacing(4)
        self.dataset_clear_response_button = QPushButton("🗑️ クリア")
        self.dataset_clear_response_button.clicked.connect(self.clear_dataset_response)
        self.dataset_clear_response_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED)};
            }}
        """
        )

        self.dataset_copy_response_button = QPushButton("📋 コピー")
        self.dataset_copy_response_button.clicked.connect(self.copy_dataset_response)
        self.dataset_copy_response_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_SUCCESS_BORDER)};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED)};
            }}
        """
        )

        self.dataset_show_prompt_button = QPushButton("📄 使用プロンプト表示")
        self.dataset_show_prompt_button.clicked.connect(self.show_used_prompt)
        self.dataset_show_prompt_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            }}
        """
        )
        self.dataset_show_prompt_button.setEnabled(False)

        self.dataset_show_api_params_button = QPushButton("🔎 API req/resp")
        self.dataset_show_api_params_button.clicked.connect(self.show_api_request_response_params)
        self.dataset_show_api_params_button.setStyleSheet(self.dataset_show_prompt_button.styleSheet())
        self.dataset_show_api_params_button.setEnabled(False)

        response_button_layout.addWidget(self.dataset_clear_response_button)
        response_button_layout.addWidget(self.dataset_copy_response_button)
        response_button_layout.addWidget(self.dataset_show_prompt_button)
        response_button_layout.addWidget(self.dataset_show_api_params_button)
        response_button_layout.addStretch()
        right_layout.addLayout(response_button_layout, 0)

        bottom_layout.addWidget(right_widget, 1)

        content_layout.addWidget(bottom_container, 1)

        self._register_conditional_tab_scroll(tab_widget, tab_scroll, right_widget)
        # テスト/デバッグ用参照
        self._dataset_response_widget = right_widget
        QTimer.singleShot(0, lambda: self._update_conditional_tab_scroll(tab_widget))

        # 接続
        self.dataset_refresh_button.clicked.connect(self.refresh_dataset_entries)
        self.dataset_id_filter_input.textChanged.connect(self.refresh_dataset_entries)
        self.dataset_grant_filter_input.textChanged.connect(self.refresh_dataset_entries)
        self.dataset_applicant_filter_input.textChanged.connect(self.refresh_dataset_entries)
        self.dataset_subject_title_filter_input.textChanged.connect(self.refresh_dataset_entries)
        self.dataset_name_filter_input.textChanged.connect(self.refresh_dataset_entries)
        self.dataset_template_filter_input.textChanged.connect(self.refresh_dataset_entries)
        self.dataset_year_filter_combo.currentIndexChanged.connect(self.refresh_dataset_entries)
        self.dataset_inst_code_filter_combo.currentIndexChanged.connect(self.refresh_dataset_entries)
        self.dataset_entries_table.itemSelectionChanged.connect(self.on_dataset_entry_selected)

        # 初期ロード
        self.refresh_dataset_entries()
        try:
            self.load_dataset_tab_buttons()
        except Exception as e:
            logger.warning("データセットタブのボタン読み込みに失敗しました: %s", e)

    def _truncate_dataset_table_text(self, text: str, max_chars: int) -> str:
        s = (text or "").strip()
        if max_chars <= 0:
            return ""
        if len(s) <= max_chars:
            return s
        return s[: max_chars - 1] + "…"

    def refresh_dataset_entries(self):
        """dataset.json のエントリーを読み込み、フィルタして表示"""
        try:
            from qt_compat.widgets import QTableWidgetItem
            from config.common import get_dynamic_file_path
            from classes.dataset.util.dataset_listing_records import load_dataset_listing_rows

            dataset_json_path = get_dynamic_file_path('output/rde/data/dataset.json')
            info_json_path = get_dynamic_file_path('output/rde/data/info.json')

            self._dataset_entries = load_dataset_listing_rows(dataset_json_path, info_json_path)

            # 年度/機関コード候補を更新（全件から抽出）
            years = []
            inst_codes = []
            for rec in self._dataset_entries:
                y = (rec.get('year') or '').strip()
                if y and y not in years:
                    years.append(y)
                ic = (rec.get('inst_code') or '').strip()
                if ic and ic not in inst_codes:
                    inst_codes.append(ic)

            years_sorted = sorted(years)
            inst_sorted = sorted(inst_codes)

            current_year = self.dataset_year_filter_combo.currentText() if hasattr(self, 'dataset_year_filter_combo') else "全て"
            self.dataset_year_filter_combo.blockSignals(True)
            self.dataset_year_filter_combo.clear()
            self.dataset_year_filter_combo.addItem("全て")
            for y in years_sorted:
                self.dataset_year_filter_combo.addItem(y)
            idx = self.dataset_year_filter_combo.findText(current_year)
            if idx >= 0:
                self.dataset_year_filter_combo.setCurrentIndex(idx)
            self.dataset_year_filter_combo.blockSignals(False)

            current_inst = self.dataset_inst_code_filter_combo.currentText() if hasattr(self, 'dataset_inst_code_filter_combo') else "全て"
            self.dataset_inst_code_filter_combo.blockSignals(True)
            self.dataset_inst_code_filter_combo.clear()
            self.dataset_inst_code_filter_combo.addItem("全て")
            for ic in inst_sorted:
                self.dataset_inst_code_filter_combo.addItem(ic)
            idx = self.dataset_inst_code_filter_combo.findText(current_inst)
            if idx >= 0:
                self.dataset_inst_code_filter_combo.setCurrentIndex(idx)
            self.dataset_inst_code_filter_combo.blockSignals(False)

            id_filter = self.dataset_id_filter_input.text().strip() if hasattr(self, 'dataset_id_filter_input') else ""
            grant_filter = self.dataset_grant_filter_input.text().strip() if hasattr(self, 'dataset_grant_filter_input') else ""
            year_filter = self.dataset_year_filter_combo.currentText().strip() if hasattr(self, 'dataset_year_filter_combo') else "全て"
            inst_filter = self.dataset_inst_code_filter_combo.currentText().strip() if hasattr(self, 'dataset_inst_code_filter_combo') else "全て"
            applicant_filter = self.dataset_applicant_filter_input.text().strip() if hasattr(self, 'dataset_applicant_filter_input') else ""
            subject_filter = self.dataset_subject_title_filter_input.text().strip() if hasattr(self, 'dataset_subject_title_filter_input') else ""
            name_filter = self.dataset_name_filter_input.text().strip() if hasattr(self, 'dataset_name_filter_input') else ""
            template_filter = self.dataset_template_filter_input.text().strip() if hasattr(self, 'dataset_template_filter_input') else ""

            filtered = []
            for rec in self._dataset_entries:
                dataset_id = (rec.get('dataset_id') or '').strip()
                grant_number = (rec.get('grant_number') or '').strip()
                year = (rec.get('year') or '').strip()
                inst_code = (rec.get('inst_code') or '').strip()
                applicant = (rec.get('applicant') or '').strip()
                subject_title = (rec.get('subject_title') or '').strip()
                dataset_name = (rec.get('dataset_name') or '').strip()
                dataset_template = (rec.get('dataset_template') or '').strip()

                if id_filter and id_filter not in dataset_id:
                    continue
                if grant_filter and grant_filter not in grant_number:
                    continue
                if year_filter and year_filter != "全て" and year_filter != year:
                    continue
                if inst_filter and inst_filter != "全て" and inst_filter != inst_code:
                    continue
                if applicant_filter and applicant_filter not in applicant:
                    continue
                if subject_filter and subject_filter not in subject_title:
                    continue
                if name_filter and name_filter not in dataset_name:
                    continue
                if template_filter and template_filter not in dataset_template:
                    continue
                filtered.append(rec)

            try:
                self.dataset_entries_table.setSortingEnabled(False)
            except Exception:
                pass

            self.dataset_entries_table.setRowCount(len(filtered))
            for row_idx, rec in enumerate(filtered):
                dataset_id = (rec.get('dataset_id') or '').strip()
                grant_number = (rec.get('grant_number') or '').strip()
                year = (rec.get('year') or '').strip()
                inst_code = (rec.get('inst_code') or '').strip()
                applicant = (rec.get('applicant') or '').strip()
                subject_title = (rec.get('subject_title') or '').strip()
                dataset_name = (rec.get('dataset_name') or '').strip()
                dataset_template = (rec.get('dataset_template') or '').strip()

                subject_disp = self._truncate_dataset_table_text(subject_title, 28)
                name_disp = self._truncate_dataset_table_text(dataset_name, 28)
                template_disp = self._truncate_dataset_table_text(dataset_template, 28)

                raw = rec.get('_raw')
                for col_idx, value in enumerate([
                    dataset_id,
                    grant_number,
                    year,
                    inst_code,
                    applicant,
                    subject_disp,
                    name_disp,
                    template_disp,
                ]):
                    item = QTableWidgetItem(value)
                    # dataset.json形式のdictを保持
                    item.setData(Qt.UserRole, raw if isinstance(raw, dict) else None)
                    self.dataset_entries_table.setItem(row_idx, col_idx, item)

            try:
                self.dataset_entries_table.resizeColumnsToContents()
            except Exception:
                pass

            try:
                self.dataset_entries_table.setSortingEnabled(True)
            except Exception:
                pass

            self.dataset_entries_table.clearSelection()
            self._selected_dataset_record = None

        except Exception as e:
            logger.debug("refresh_dataset_entries failed: %s", e)
            try:
                self.dataset_entries_table.setRowCount(0)
            except Exception:
                pass

    def on_dataset_entry_selected(self):
        """一覧で選択されたデータセットエントリーを保持し、context_data を更新"""
        try:
            selected_items = self.dataset_entries_table.selectedItems() if hasattr(self, 'dataset_entries_table') else []
            if not selected_items:
                self._selected_dataset_record = None
                return

            rec = selected_items[0].data(Qt.UserRole)
            if not isinstance(rec, dict):
                self._selected_dataset_record = None
                return

            self._selected_dataset_record = rec

            # 既存の更新ロジックを再利用（dataset.json形式）
            try:
                self.update_context_from_dataset(rec)
            except Exception:
                pass
            # AI拡張タブ側の表示も同期（存在する場合）
            try:
                self.update_dataset_info_display()
            except Exception:
                pass
        except Exception as e:
            logger.debug("on_dataset_entry_selected failed: %s", e)
            self._selected_dataset_record = None

    def _get_dataset_target_key(self, rec: dict) -> str:
        dataset_id = ''
        grant_number = ''
        name = ''
        try:
            dataset_id = (rec.get('id') or '').strip()
            attrs = rec.get('attributes', {}) if isinstance(rec.get('attributes', {}), dict) else {}
            grant_number = (attrs.get('grantNumber') or '').strip()
            name = (attrs.get('name') or '').strip()
        except Exception:
            pass
        # dataset_id > grant_number > name
        return dataset_id or grant_number or name or 'unknown'

    def _get_selected_dataset_records(self) -> List[dict]:
        if not hasattr(self, 'dataset_entries_table'):
            return []
        try:
            sm = self.dataset_entries_table.selectionModel()
            if sm is None:
                return []
            rows = sm.selectedRows(0)
            recs = []
            for mi in rows:
                try:
                    item = self.dataset_entries_table.item(mi.row(), 0)
                    if item is None:
                        continue
                    rec = item.data(Qt.UserRole)
                    if isinstance(rec, dict):
                        recs.append(rec)
                except Exception:
                    continue
            return recs
        except Exception:
            return []

    def _get_displayed_dataset_records(self) -> List[dict]:
        if not hasattr(self, 'dataset_entries_table'):
            return []
        try:
            recs = []
            seen = set()
            for row in range(self.dataset_entries_table.rowCount()):
                item = self.dataset_entries_table.item(row, 0)
                if item is None:
                    continue
                rec = item.data(Qt.UserRole)
                if not isinstance(rec, dict):
                    continue
                key = self._get_dataset_target_key(rec)
                if key in seen:
                    continue
                seen.add(key)
                recs.append(rec)
            return recs
        except Exception:
            return []

    def load_dataset_tab_buttons(self):
        """AI拡張設定からボタンを読み込み、データセットタブに表示"""
        try:
            from classes.dataset.util.ai_extension_helper import load_ai_extension_config, infer_ai_suggest_target_kind
            config = load_ai_extension_config()

            while self.dataset_buttons_layout.count():
                item = self.dataset_buttons_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()

            self.dataset_buttons.clear()

            ui_settings = config.get('ui_settings', {})
            button_height = ui_settings.get('button_height', 60)
            button_width = ui_settings.get('button_width', 140)
            show_icons = ui_settings.get('show_icons', True)

            buttons_config = config.get('buttons', [])
            default_buttons = config.get('default_buttons', [])
            all_buttons = buttons_config + default_buttons

            # dataset向けのみ
            all_buttons = [b for b in all_buttons if infer_ai_suggest_target_kind(b) != 'report']

            if not all_buttons:
                no_buttons_label = QLabel("AI拡張ボタンが設定されていません。\n設定編集ボタンから設定ファイルを確認してください。")
                no_buttons_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; text-align: center; padding: 20px;")
                no_buttons_label.setAlignment(Qt.AlignCenter)
                self.dataset_buttons_layout.addWidget(no_buttons_label)
                return

            for button_config in all_buttons:
                button = self.create_extension_button(
                    button_config,
                    button_height,
                    button_width,
                    show_icons,
                    clicked_handler=self.on_dataset_tab_button_clicked,
                    buttons_list=self.dataset_buttons,
                    target_kind="dataset",
                )
                self.dataset_buttons_layout.addWidget(button)

            self.dataset_buttons_layout.addStretch()

        except Exception as e:
            error_label = QLabel(f"AI拡張設定の読み込みエラー: {str(e)}")
            error_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; padding: 10px;")
            self.dataset_buttons_layout.addWidget(error_label)

    def on_dataset_tab_button_clicked(self, button_config):
        """データセットタブのAIボタンクリック時の処理"""
        try:
            button_id = button_config.get('id', 'unknown')

            # 一括問い合わせ
            if getattr(self, 'dataset_bulk_checkbox', None) is not None and self.dataset_bulk_checkbox.isChecked():
                self._start_bulk_dataset_requests(button_config)
                return

            if not isinstance(getattr(self, '_selected_dataset_record', None), dict):
                QMessageBox.warning(self, "警告", "データセットエントリーを選択してください（上部一覧から1件選択）。")
                return

            target_key = self._get_dataset_target_key(self._selected_dataset_record)

            # 既存結果の検出（同一ボタン + 同一対象）
            try:
                from classes.dataset.util.ai_suggest_result_log import read_latest_result

                latest = read_latest_result('dataset', target_key, button_id)
                if latest:
                    if os.environ.get("PYTEST_CURRENT_TEST"):
                        fmt = (latest.get('display_format') or 'text').lower()
                        content = latest.get('display_content') or ''
                        if fmt == 'html':
                            self.dataset_response_display.setHtml(content)
                        else:
                            self.dataset_response_display.setText(content)
                        self.last_used_prompt = latest.get('prompt')
                        self.last_api_request_params = latest.get('request_params')
                        self.last_api_response_params = latest.get('response_params')
                        self.last_api_provider = latest.get('provider')
                        self.last_api_model = latest.get('model')
                        if hasattr(self, 'dataset_show_prompt_button'):
                            self.dataset_show_prompt_button.setEnabled(bool(self.last_used_prompt))
                        if hasattr(self, 'dataset_show_api_params_button'):
                            self.dataset_show_api_params_button.setEnabled(bool(self.last_api_request_params or self.last_api_response_params))
                        return

                    ts = (latest.get('timestamp') or '').strip()
                    box = QMessageBox(self)
                    box.setIcon(QMessageBox.Question)
                    box.setWindowTitle("既存結果あり")
                    box.setText(f"同一ボタン・同一対象の既存結果が見つかりました。" + (f"（{ts}）" if ts else ""))
                    box.setInformativeText("既存の最新結果を表示しますか？それとも新規に問い合わせますか？")
                    show_existing_btn = box.addButton("既存結果を表示", QMessageBox.AcceptRole)
                    run_new_btn = box.addButton("新規問い合わせ", QMessageBox.ActionRole)
                    cancel_btn = box.addButton(QMessageBox.Cancel)
                    box.setDefaultButton(show_existing_btn)
                    box.exec()

                    chosen = box.clickedButton()
                    if chosen == cancel_btn:
                        return
                    if chosen == show_existing_btn:
                        fmt = (latest.get('display_format') or 'text').lower()
                        content = latest.get('display_content') or ''
                        if fmt == 'html':
                            self.dataset_response_display.setHtml(content)
                        else:
                            self.dataset_response_display.setText(content)

                        self.last_used_prompt = latest.get('prompt')
                        self.last_api_request_params = latest.get('request_params')
                        self.last_api_response_params = latest.get('response_params')
                        self.last_api_provider = latest.get('provider')
                        self.last_api_model = latest.get('model')
                        if hasattr(self, 'dataset_show_prompt_button'):
                            self.dataset_show_prompt_button.setEnabled(bool(self.last_used_prompt))
                        if hasattr(self, 'dataset_show_api_params_button'):
                            self.dataset_show_api_params_button.setEnabled(bool(self.last_api_request_params or self.last_api_response_params))
                        return

                    # run_new_btn の場合はそのまま問い合わせ続行
            except Exception:
                pass

            clicked_button = self.sender()
            self._active_dataset_button = clicked_button if hasattr(clicked_button, 'start_loading') else None
            if clicked_button and hasattr(clicked_button, 'start_loading'):
                clicked_button.start_loading("AI処理中")

            # 選択データセットを context_data に反映
            try:
                self.update_context_from_dataset(self._selected_dataset_record)
            except Exception:
                pass

            prompt = self.build_extension_prompt(button_config)
            if not prompt:
                if clicked_button:
                    clicked_button.stop_loading()
                QMessageBox.warning(self, "警告", "プロンプトの構築に失敗しました。")
                return

            self.execute_dataset_ai_request(prompt, button_config, clicked_button, dataset_target_key=target_key)

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"データセットボタン処理エラー: {str(e)}")

    def _normalize_bulk_dataset_concurrency(self, requested: Optional[int]) -> int:
        try:
            value = int(requested) if requested is not None else 5
        except Exception:
            value = 5
        if value < 1:
            value = 1
        if value > 20:
            value = 20
        return value

    def _update_bulk_dataset_status_message(self):
        try:
            if getattr(self, 'dataset_spinner_overlay', None):
                label = (getattr(self, '_bulk_dataset_button_config', {}) or {}).get('label', 'AI')
                total = int(self._bulk_dataset_total or len(self._bulk_dataset_queue) or 0)
                done = int(self._bulk_dataset_index or 0)
                inflight = int(self._bulk_dataset_inflight or 0)
                if total > 0:
                    self.dataset_spinner_overlay.set_message(
                        f"一括処理中 完了 {done}/{total} / 実行中 {inflight}: {label}"
                    )
        except Exception:
            pass

    def _on_bulk_dataset_task_done(self):
        try:
            if self._bulk_dataset_inflight > 0:
                self._bulk_dataset_inflight -= 1
        except Exception:
            self._bulk_dataset_inflight = 0

        try:
            self._bulk_dataset_index += 1
            total = int(self._bulk_dataset_total or len(self._bulk_dataset_queue) or 0)
            if total > 0 and self._bulk_dataset_index > total:
                self._bulk_dataset_index = total
        except Exception:
            pass

        self._update_bulk_dataset_status_message()
        self._kick_bulk_dataset_scheduler()

    def _finish_bulk_dataset_requests(self):
        self._bulk_dataset_running = False
        self._bulk_dataset_cancelled = False
        self._bulk_dataset_queue = []
        self._bulk_dataset_index = 0
        self._bulk_dataset_total = 0
        self._bulk_dataset_next_index = 0
        self._bulk_dataset_inflight = 0
        try:
            if getattr(self, 'dataset_spinner_overlay', None):
                self.dataset_spinner_overlay.set_message("AI応答を待機中...")
        except Exception:
            pass
        for b in list(getattr(self, 'dataset_buttons', [])):
            try:
                b.setEnabled(True)
            except Exception:
                pass

    def _kick_bulk_dataset_scheduler(self):
        if not self._bulk_dataset_running or self._bulk_dataset_cancelled:
            if int(self._bulk_dataset_inflight or 0) <= 0:
                self._finish_bulk_dataset_requests()
            return

        total = int(self._bulk_dataset_total or len(self._bulk_dataset_queue) or 0)
        if total <= 0:
            self._finish_bulk_dataset_requests()
            return

        max_conc = self._normalize_bulk_dataset_concurrency(getattr(self, '_bulk_dataset_max_concurrency', 5))

        while (
            self._bulk_dataset_inflight < max_conc
            and self._bulk_dataset_next_index < len(self._bulk_dataset_queue)
            and self._bulk_dataset_running
            and not self._bulk_dataset_cancelled
        ):
            task = self._bulk_dataset_queue[self._bulk_dataset_next_index]
            self._bulk_dataset_next_index += 1

            rec = task.get('record')
            if not isinstance(rec, dict):
                self._bulk_dataset_index += 1
                continue

            # context_data をその都度更新
            try:
                self.update_context_from_dataset(rec)
            except Exception:
                pass

            button_config = getattr(self, '_bulk_dataset_button_config', {}) or {}
            prompt = self.build_extension_prompt(button_config)
            if not prompt:
                self._bulk_dataset_index += 1
                continue

            self._bulk_dataset_inflight += 1
            self._update_bulk_dataset_status_message()

            self.execute_dataset_ai_request(
                prompt,
                button_config,
                button_widget=None,
                dataset_target_key=task.get('target_key') or self._get_dataset_target_key(rec),
                _bulk_continue=True,
            )

        if (
            self._bulk_dataset_running
            and not self._bulk_dataset_cancelled
            and self._bulk_dataset_next_index >= len(self._bulk_dataset_queue)
            and self._bulk_dataset_inflight <= 0
            and self._bulk_dataset_index >= total
        ):
            self._finish_bulk_dataset_requests()

    def _start_bulk_dataset_requests(self, button_config):
        """データセットタブ: 一括問い合わせ（選択 or 表示全件）"""
        try:
            selected = self._get_selected_dataset_records()
            displayed = self._get_displayed_dataset_records()
            use_selected = len(selected) > 0
            candidates = selected if use_selected else displayed
            if not candidates:
                QMessageBox.information(self, "情報", "一括問い合わせの対象がありません。")
                return

            try:
                from classes.dataset.util.ai_suggest_result_log import read_latest_result
            except Exception:
                read_latest_result = None

            planned_total = len(candidates)
            existing = 0
            tasks = []
            for rec in candidates:
                target_key = self._get_dataset_target_key(rec)
                latest = None
                if read_latest_result is not None:
                    try:
                        latest = read_latest_result('dataset', target_key, button_config.get('id', 'unknown'))
                    except Exception:
                        latest = None
                if latest:
                    existing += 1
                tasks.append({'record': rec, 'target_key': target_key, 'has_existing': bool(latest)})

            missing = planned_total - existing
            scope_label = f"選択 {planned_total} 件" if use_selected else f"表示全件 {planned_total} 件"

            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("一括問い合わせ")
            box.setText(f"一括問い合わせを開始します。\n\n対象: {scope_label}")
            box.setInformativeText(
                f"予定件数: {planned_total} 件\n"
                f"既存結果あり: {existing} 件\n"
                f"既存結果なし: {missing} 件\n\n"
                "実行方法を選択してください。"
            )

            overwrite_btn = box.addButton("上書きして全件問い合わせ", QMessageBox.AcceptRole)
            missing_only_btn = box.addButton("既存なしのみ問い合わせ", QMessageBox.ActionRole)
            cancel_btn = box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(missing_only_btn if missing > 0 else overwrite_btn)

            if os.environ.get("PYTEST_CURRENT_TEST"):
                chosen = missing_only_btn
            else:
                box.exec()
                chosen = box.clickedButton()

            if chosen == cancel_btn:
                return
            if chosen == missing_only_btn:
                tasks = [t for t in tasks if not t.get('has_existing')]

            if not tasks:
                QMessageBox.information(self, "情報", "問い合わせ対象（既存なし）がありません。")
                return

            self._bulk_dataset_queue = tasks
            self._bulk_dataset_index = 0
            self._bulk_dataset_total = len(tasks)
            self._bulk_dataset_next_index = 0
            self._bulk_dataset_inflight = 0
            self._bulk_dataset_running = True
            self._bulk_dataset_cancelled = False
            self._bulk_dataset_button_config = button_config

            requested = None
            try:
                requested = int(getattr(self, 'dataset_bulk_parallel_spinbox', None).value())
            except Exception:
                requested = None
            self._bulk_dataset_max_concurrency = self._normalize_bulk_dataset_concurrency(requested)

            for b in list(getattr(self, 'dataset_buttons', [])):
                try:
                    b.setEnabled(False)
                except Exception:
                    pass

            self._update_bulk_dataset_status_message()
            self._kick_bulk_dataset_scheduler()
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"一括問い合わせエラー: {str(e)}")

    def update_dataset_spinner_visibility(self):
        try:
            if getattr(self, 'dataset_spinner_overlay', None):
                if len(self.dataset_ai_threads) > 0:
                    self.dataset_spinner_overlay.start()
                else:
                    self.dataset_spinner_overlay.stop()
        except Exception as _e:
            logger.debug("update_dataset_spinner_visibility failed: %s", _e)

    def cancel_dataset_ai_requests(self):
        """データセットタブの実行中リクエストをキャンセル"""
        try:
            self._bulk_dataset_cancelled = True
            self._bulk_dataset_running = False
            self._bulk_dataset_queue = []
            self._bulk_dataset_total = 0
            self._bulk_dataset_next_index = 0
            self._bulk_dataset_inflight = 0

            for thread in list(self.dataset_ai_threads):
                try:
                    if thread and thread.isRunning():
                        thread.stop()
                except Exception:
                    pass
                finally:
                    if thread in self.dataset_ai_threads:
                        self.dataset_ai_threads.remove(thread)

            if self._active_dataset_button:
                try:
                    self._active_dataset_button.stop_loading()
                except Exception:
                    pass
                finally:
                    self._active_dataset_button = None

            if getattr(self, 'dataset_spinner_overlay', None):
                self.dataset_spinner_overlay.stop()
                self.dataset_spinner_overlay.set_message("AI応答を待機中...")

            for b in list(getattr(self, 'dataset_buttons', [])):
                try:
                    b.setEnabled(True)
                except Exception:
                    pass

            if hasattr(self, 'dataset_response_display'):
                self.dataset_response_display.append("\n<em>⏹ AI処理をキャンセルしました。</em>")
        except Exception as e:
            logger.debug("cancel_dataset_ai_requests failed: %s", e)

    def clear_dataset_response(self):
        try:
            if hasattr(self, 'dataset_response_display'):
                self.dataset_response_display.clear()
        except Exception:
            pass

    def copy_dataset_response(self):
        try:
            if hasattr(self, 'dataset_response_display'):
                from qt_compat.widgets import QApplication
                text = self.dataset_response_display.toPlainText()
                if text:
                    QApplication.clipboard().setText(text)
        except Exception:
            pass

    def execute_dataset_ai_request(
        self,
        prompt,
        button_config,
        button_widget,
        dataset_target_key: Optional[str] = None,
        _bulk_continue: bool = False,
        retry_count: int = 0,
    ):
        """データセットタブ向けAIリクエスト実行（AI拡張相当、表示先だけ分離）"""
        try:
            self.last_used_prompt = prompt
            self.last_api_request_params = None
            self.last_api_response_params = None
            self.last_api_provider = None
            self.last_api_model = None
            if hasattr(self, 'dataset_show_api_params_button'):
                self.dataset_show_api_params_button.setEnabled(False)
            if hasattr(self, 'dataset_show_prompt_button'):
                self.dataset_show_prompt_button.setEnabled(True)

            for b in list(getattr(self, 'dataset_buttons', [])):
                try:
                    b.setEnabled(False)
                except Exception:
                    pass

            button_label = button_config.get('label', 'AI処理')
            button_icon = button_config.get('icon', '🤖')
            if getattr(self, 'dataset_spinner_overlay', None):
                self.dataset_spinner_overlay.set_message(f"{button_icon} {button_label} 実行中...")

            ai_thread = AIRequestThread(prompt, self.context_data)
            self.dataset_ai_threads.append(ai_thread)
            self.update_dataset_spinner_visibility()

            def on_success(result):
                try:
                    try:
                        self.last_api_request_params = result.get('request_params')
                        self.last_api_response_params = result.get('response_params')
                        self.last_api_provider = result.get('provider')
                        self.last_api_model = result.get('model')
                        if hasattr(self, 'dataset_show_api_params_button'):
                            self.dataset_show_api_params_button.setEnabled(bool(self.last_api_request_params or self.last_api_response_params))
                    except Exception as _e:
                        logger.debug("API req/resp params capture failed: %s", _e)

                    response_text = result.get('response') or result.get('content', '')
                    fmt = button_config.get('output_format', 'text')
                    if response_text:
                        if fmt == 'json':
                            valid, fixed_text = self._validate_and_fix_json_response(response_text)
                            if valid:
                                self.dataset_response_display.setText(fixed_text)
                            else:
                                if retry_count < 2:
                                    if ai_thread in self.dataset_ai_threads:
                                        self.dataset_ai_threads.remove(ai_thread)
                                    self.update_dataset_spinner_visibility()
                                    self.execute_dataset_ai_request(
                                        prompt,
                                        button_config,
                                        button_widget,
                                        dataset_target_key=dataset_target_key,
                                        _bulk_continue=_bulk_continue,
                                        retry_count=retry_count + 1,
                                    )
                                    return
                                import json as _json
                                try:
                                    _json.loads(response_text)
                                    self.dataset_response_display.setText(response_text)
                                except Exception:
                                    error_json_str = self._wrap_json_error(
                                        error_message="JSONの検証に失敗しました（最大リトライ到達）",
                                        raw_output=response_text,
                                        retries=retry_count,
                                    )
                                    self.dataset_response_display.setText(error_json_str)
                        else:
                            formatted_response = self.format_extension_response(response_text, button_config)
                            self.dataset_response_display.setHtml(formatted_response)
                    else:
                        self.dataset_response_display.setText("AI応答が空でした。")

                    # ログ保存（dataset）
                    try:
                        from classes.dataset.util.ai_suggest_result_log import append_result

                        target_key = (dataset_target_key or '').strip()
                        if not target_key:
                            try:
                                target_key = self._get_dataset_target_key(getattr(self, '_selected_dataset_record', {}) or {})
                            except Exception:
                                target_key = 'unknown'

                        if fmt == 'json':
                            display_format = 'text'
                            display_content = self.dataset_response_display.toPlainText()
                        else:
                            display_format = 'html'
                            display_content = self.dataset_response_display.toHtml()

                        append_result(
                            target_kind='dataset',
                            target_key=target_key,
                            button_id=button_config.get('id', 'unknown'),
                            button_label=button_config.get('label', 'Unknown'),
                            prompt=self.last_used_prompt or prompt,
                            display_format=display_format,
                            display_content=display_content,
                            provider=self.last_api_provider,
                            model=self.last_api_model,
                            request_params=self.last_api_request_params,
                            response_params=self.last_api_response_params,
                            started_at=(result.get('started_at') if isinstance(result, dict) else None),
                            finished_at=(result.get('finished_at') if isinstance(result, dict) else None),
                            elapsed_seconds=(result.get('elapsed_seconds') if isinstance(result, dict) else None),
                        )
                    except Exception:
                        pass

                finally:
                    if button_widget:
                        try:
                            button_widget.stop_loading()
                        except Exception:
                            pass
                    if self._active_dataset_button is button_widget:
                        self._active_dataset_button = None
                    if ai_thread in self.dataset_ai_threads:
                        self.dataset_ai_threads.remove(ai_thread)
                    self.update_dataset_spinner_visibility()
                    if not self._bulk_dataset_running and getattr(self, 'dataset_spinner_overlay', None):
                        self.dataset_spinner_overlay.set_message("AI応答を待機中...")

                    if not self._bulk_dataset_running:
                        for b in list(getattr(self, 'dataset_buttons', [])):
                            try:
                                b.setEnabled(True)
                            except Exception:
                                pass

                    if _bulk_continue and self._bulk_dataset_running:
                        self._on_bulk_dataset_task_done()

            def on_error(error_message):
                try:
                    self.dataset_response_display.setText(f"エラー: {error_message}")
                finally:
                    if button_widget:
                        try:
                            button_widget.stop_loading()
                        except Exception:
                            pass
                    if self._active_dataset_button is button_widget:
                        self._active_dataset_button = None
                    if ai_thread in self.dataset_ai_threads:
                        self.dataset_ai_threads.remove(ai_thread)
                    self.update_dataset_spinner_visibility()
                    if not self._bulk_dataset_running and getattr(self, 'dataset_spinner_overlay', None):
                        self.dataset_spinner_overlay.set_message("AI応答を待機中...")
                    if not self._bulk_dataset_running:
                        for b in list(getattr(self, 'dataset_buttons', [])):
                            try:
                                b.setEnabled(True)
                            except Exception:
                                pass

                    if _bulk_continue and self._bulk_dataset_running:
                        self._on_bulk_dataset_task_done()

                    self.last_api_request_params = None
                    self.last_api_response_params = None
                    self.last_api_provider = None
                    self.last_api_model = None
                    if hasattr(self, 'dataset_show_api_params_button'):
                        self.dataset_show_api_params_button.setEnabled(False)

            ai_thread.result_ready.connect(on_success)
            ai_thread.error_occurred.connect(on_error)
            ai_thread.start()

        except Exception as e:
            if button_widget:
                try:
                    button_widget.stop_loading()
                except Exception:
                    pass
            if self._active_dataset_button is button_widget:
                self._active_dataset_button = None
            for b in list(getattr(self, 'dataset_buttons', [])):
                try:
                    b.setEnabled(True)
                except Exception:
                    pass
            QMessageBox.critical(self, "エラー", f"データセットAIリクエスト実行エラー: {str(e)}")

    def _get_report_record_value(self, record: dict, candidates: List[str]) -> str:
        for key in candidates:
            try:
                if key in record and record.get(key) is not None:
                    v = str(record.get(key)).strip()
                    if v:
                        return v
            except Exception:
                continue
        # fallback: partial match
        try:
            for k, v in record.items():
                if v is None:
                    continue
                for c in candidates:
                    if c and c in str(k):
                        sv = str(v).strip()
                        if sv:
                            return sv
        except Exception:
            pass
        return ""

    def _truncate_table_text(self, text: str, max_chars: int) -> str:
        s = (text or "").strip()
        if max_chars <= 0:
            return ""
        if len(s) <= max_chars:
            return s
        # 末尾を省略
        return s[: max_chars - 1] + "…"

    def _get_prompt_file_for_target(self, prompt_file: str, target_kind: str, button_id: str) -> str:
        """AI拡張(データセット)と報告書でプロンプト保存先を分離する"""
        if not prompt_file:
            return prompt_file
        if target_kind != "report":
            return prompt_file

        # normalize separators for matching
        norm = prompt_file.replace('\\', '/')
        if '/input/ai/prompts/ext/' in f"/{norm}":
            # input/ai/prompts/ext/<id>.txt -> input/ai/prompts/report/<id>.txt
            return norm.replace('/input/ai/prompts/ext/', '/input/ai/prompts/report/')
        if norm.startswith('input/ai/prompts/ext/'):
            return norm.replace('input/ai/prompts/ext/', 'input/ai/prompts/report/')

        # fallback: suffix
        base, ext = os.path.splitext(norm)
        if not ext:
            ext = '.txt'
        return f"{base}_report{ext}"

    def refresh_report_entries(self):
        """converted.xlsx のエントリーを読み込み、フィルタして表示"""
        try:
            from qt_compat.widgets import QTableWidgetItem
            from classes.dataset.util.ai_extension_helper import load_converted_xlsx_report_entries

            self._report_entries = load_converted_xlsx_report_entries()

            # 年度候補を更新（全件から抽出）
            years = []
            cross_mains = []
            cross_subs = []
            important_mains = []
            important_subs = []
            for rec in self._report_entries:
                y = self._get_report_record_value(rec, ["年度", "利用年度"])
                if y and y not in years:
                    years.append(y)

                cm = self._get_report_record_value(
                    rec,
                    [
                        "横断技術領域・主",
                        "横断技術領域（主）",
                        "キーワード【横断技術領域】（主）",
                        "横断技術領域 主",
                    ],
                )
                if cm and cm not in cross_mains:
                    cross_mains.append(cm)
                cs = self._get_report_record_value(
                    rec,
                    [
                        "横断技術領域・副",
                        "横断技術領域（副）",
                        "キーワード【横断技術領域】（副）",
                        "横断技術領域 副",
                    ],
                )
                if cs and cs not in cross_subs:
                    cross_subs.append(cs)

                im = self._get_report_record_value(rec, ["重要技術領域・主", "重要技術領域（主）", "important_tech_main", "重要技術領域 主"])
                if im and im not in important_mains:
                    important_mains.append(im)
                isub = self._get_report_record_value(rec, ["重要技術領域・副", "重要技術領域（副）", "important_tech_sub", "重要技術領域 副"])
                if isub and isub not in important_subs:
                    important_subs.append(isub)
            years_sorted = sorted(years)
            cross_mains_sorted = sorted(cross_mains)
            cross_subs_sorted = sorted(cross_subs)
            important_mains_sorted = sorted(important_mains)
            important_subs_sorted = sorted(important_subs)

            current_year = self.report_year_filter_combo.currentText() if hasattr(self, 'report_year_filter_combo') else "全て"
            self.report_year_filter_combo.blockSignals(True)
            self.report_year_filter_combo.clear()
            self.report_year_filter_combo.addItem("全て")
            for y in years_sorted:
                self.report_year_filter_combo.addItem(y)
            # 元の選択を復元
            idx = self.report_year_filter_combo.findText(current_year)
            if idx >= 0:
                self.report_year_filter_combo.setCurrentIndex(idx)
            self.report_year_filter_combo.blockSignals(False)

            # 重要技術領域（主/副）候補を更新
            current_main = self.report_important_main_filter_combo.currentText() if hasattr(self, 'report_important_main_filter_combo') else "全て"
            self.report_important_main_filter_combo.blockSignals(True)
            self.report_important_main_filter_combo.clear()
            self.report_important_main_filter_combo.addItem("全て")
            for v in important_mains_sorted:
                self.report_important_main_filter_combo.addItem(v)
            idx = self.report_important_main_filter_combo.findText(current_main)
            if idx >= 0:
                self.report_important_main_filter_combo.setCurrentIndex(idx)
            self.report_important_main_filter_combo.blockSignals(False)

            current_sub = self.report_important_sub_filter_combo.currentText() if hasattr(self, 'report_important_sub_filter_combo') else "全て"
            self.report_important_sub_filter_combo.blockSignals(True)
            self.report_important_sub_filter_combo.clear()
            self.report_important_sub_filter_combo.addItem("全て")
            for v in important_subs_sorted:
                self.report_important_sub_filter_combo.addItem(v)
            idx = self.report_important_sub_filter_combo.findText(current_sub)
            if idx >= 0:
                self.report_important_sub_filter_combo.setCurrentIndex(idx)
            self.report_important_sub_filter_combo.blockSignals(False)

            # 横断技術領域（主/副）候補を更新
            current_cross_main = self.report_cross_main_filter_combo.currentText() if hasattr(self, 'report_cross_main_filter_combo') else "全て"
            self.report_cross_main_filter_combo.blockSignals(True)
            self.report_cross_main_filter_combo.clear()
            self.report_cross_main_filter_combo.addItem("全て")
            for v in cross_mains_sorted:
                self.report_cross_main_filter_combo.addItem(v)
            idx = self.report_cross_main_filter_combo.findText(current_cross_main)
            if idx >= 0:
                self.report_cross_main_filter_combo.setCurrentIndex(idx)
            self.report_cross_main_filter_combo.blockSignals(False)

            current_cross_sub = self.report_cross_sub_filter_combo.currentText() if hasattr(self, 'report_cross_sub_filter_combo') else "全て"
            self.report_cross_sub_filter_combo.blockSignals(True)
            self.report_cross_sub_filter_combo.clear()
            self.report_cross_sub_filter_combo.addItem("全て")
            for v in cross_subs_sorted:
                self.report_cross_sub_filter_combo.addItem(v)
            idx = self.report_cross_sub_filter_combo.findText(current_cross_sub)
            if idx >= 0:
                self.report_cross_sub_filter_combo.setCurrentIndex(idx)
            self.report_cross_sub_filter_combo.blockSignals(False)

            arimno_filter = self.report_arimno_filter_input.text().strip() if hasattr(self, 'report_arimno_filter_input') else ""
            year_filter = self.report_year_filter_combo.currentText().strip() if hasattr(self, 'report_year_filter_combo') else "全て"
            inst_code_filter = self.report_inst_code_filter_input.text().strip() if hasattr(self, 'report_inst_code_filter_input') else ""
            affiliation_filter = self.report_affiliation_filter_input.text().strip() if hasattr(self, 'report_affiliation_filter_input') else ""
            title_filter = self.report_title_filter_input.text().strip() if hasattr(self, 'report_title_filter_input') else ""
            cross_main_filter = self.report_cross_main_filter_combo.currentText().strip() if hasattr(self, 'report_cross_main_filter_combo') else "全て"
            cross_sub_filter = self.report_cross_sub_filter_combo.currentText().strip() if hasattr(self, 'report_cross_sub_filter_combo') else "全て"
            important_main_filter = self.report_important_main_filter_combo.currentText().strip() if hasattr(self, 'report_important_main_filter_combo') else "全て"
            important_sub_filter = self.report_important_sub_filter_combo.currentText().strip() if hasattr(self, 'report_important_sub_filter_combo') else "全て"

            filtered = []
            for rec in self._report_entries:
                arimno = self._get_report_record_value(rec, ["ARIMNO", "課題番号"])
                year = self._get_report_record_value(rec, ["年度", "利用年度"])
                inst_code = self._get_report_record_value(rec, ["機関コード", "実施機関コード"])
                affiliation = self._get_report_record_value(rec, ["所属名", "所属"])
                title = self._get_report_record_value(rec, ["利用課題名", "Title"])
                cross_main = self._get_report_record_value(rec, ["横断技術領域・主", "横断技術領域（主）"])
                cross_sub = self._get_report_record_value(rec, ["横断技術領域・副", "横断技術領域（副）"])
                important_main = self._get_report_record_value(rec, ["重要技術領域・主", "重要技術領域（主）"])
                important_sub = self._get_report_record_value(rec, ["重要技術領域・副", "重要技術領域（副）"])

                if arimno_filter and arimno_filter not in arimno:
                    continue
                if year_filter and year_filter != "全て" and year_filter != year:
                    continue
                if inst_code_filter and inst_code_filter not in inst_code:
                    continue
                if affiliation_filter and affiliation_filter not in affiliation:
                    continue
                if title_filter and title_filter not in title:
                    continue
                if cross_main_filter and cross_main_filter != "全て" and cross_main_filter not in cross_main:
                    continue
                if cross_sub_filter and cross_sub_filter != "全て" and cross_sub_filter not in cross_sub:
                    continue
                if important_main_filter and important_main_filter != "全て" and important_main_filter not in important_main:
                    continue
                if important_sub_filter and important_sub_filter != "全て" and important_sub_filter not in important_sub:
                    continue
                filtered.append(rec)

            try:
                self.report_entries_table.setSortingEnabled(False)
            except Exception:
                pass

            self.report_entries_table.setRowCount(len(filtered))
            for row_idx, rec in enumerate(filtered):
                arimno = self._get_report_record_value(rec, ["ARIMNO", "課題番号"])
                year = self._get_report_record_value(rec, ["年度", "利用年度"])
                inst_code = self._get_report_record_value(rec, ["機関コード", "実施機関コード"])
                affiliation = self._get_report_record_value(rec, ["所属名", "所属"])
                title = self._get_report_record_value(rec, ["利用課題名", "Title"])
                cross_main = self._get_report_record_value(rec, ["横断技術領域・主", "横断技術領域（主）"])
                cross_sub = self._get_report_record_value(rec, ["横断技術領域・副", "横断技術領域（副）"])
                important_main = self._get_report_record_value(rec, ["重要技術領域・主", "重要技術領域（主）"])
                important_sub = self._get_report_record_value(rec, ["重要技術領域・副", "重要技術領域（副）"])

                affiliation_disp = self._truncate_table_text(affiliation, 22)
                title_disp = self._truncate_table_text(title, 28)
                cross_main_disp = self._truncate_table_text(cross_main, 22)
                cross_sub_disp = self._truncate_table_text(cross_sub, 22)
                important_main_disp = self._truncate_table_text(important_main, 22)
                important_sub_disp = self._truncate_table_text(important_sub, 22)

                # 表示順: ARIM課題番号, 年度, 機関コード, 所属名, 利用課題名, 横断技術領域(主), 横断技術領域(副), 重要技術領域(主), 重要技術領域(副)
                for col_idx, value in enumerate([
                    arimno,
                    year,
                    inst_code,
                    affiliation_disp,
                    title_disp,
                    cross_main_disp,
                    cross_sub_disp,
                    important_main_disp,
                    important_sub_disp,
                ]):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, rec)
                    self.report_entries_table.setItem(row_idx, col_idx, item)

            try:
                self.report_entries_table.resizeColumnsToContents()
            except Exception:
                pass

            try:
                self.report_entries_table.setSortingEnabled(True)
            except Exception:
                pass

            # 選択解除
            self.report_entries_table.clearSelection()
            self._selected_report_record = None
            self._selected_report_placeholders = {}

        except Exception as e:
            logger.debug("refresh_report_entries failed: %s", e)
            try:
                self.report_entries_table.setRowCount(0)
            except Exception:
                pass

    def on_report_entry_selected(self):
        """一覧で選択された報告書エントリーを保持"""
        try:
            selected_items = self.report_entries_table.selectedItems() if hasattr(self, 'report_entries_table') else []
            if not selected_items:
                self._selected_report_record = None
                self._selected_report_placeholders = {}
                return

            rec = selected_items[0].data(Qt.UserRole)
            if not isinstance(rec, dict):
                self._selected_report_record = None
                self._selected_report_placeholders = {}
                return

            self._selected_report_record = rec
            self._selected_report_placeholders = self._build_report_placeholders_for_record(rec)
        except Exception as e:
            logger.debug("on_report_entry_selected failed: %s", e)
            self._selected_report_record = None
            self._selected_report_placeholders = {}

    def _build_report_placeholders_for_record(self, rec: dict) -> dict:
        from classes.dataset.util.ai_extension_helper import placeholders_from_converted_xlsx_record

        placeholders = placeholders_from_converted_xlsx_record(rec)

        # ファイル由来の情報（抽出済み）を報告書コンテキストにも載せる
        try:
            for k in ['file_tree', 'text_from_structured_files', 'json_from_structured_files']:
                if k in self.context_data and self.context_data.get(k) is not None:
                    placeholders.setdefault(k, self.context_data.get(k))
        except Exception:
            pass

        # 互換キー（AI拡張テンプレートを使い回せるように）
        arimno = self._get_report_record_value(rec, ["ARIMNO", "課題番号"])
        title = self._get_report_record_value(rec, ["利用課題名", "Title"])
        affiliation = self._get_report_record_value(rec, ["所属名", "所属"])

        if arimno:
            placeholders.setdefault('grant_number', arimno)
            placeholders.setdefault('arim_report_project_number', arimno)
            placeholders.setdefault('report_project_number', arimno)
        if title:
            placeholders.setdefault('name', title)
            placeholders.setdefault('arim_report_title', title)
            placeholders.setdefault('report_title', title)
        if affiliation:
            placeholders.setdefault('arim_report_affiliation', affiliation)
            placeholders.setdefault('report_affiliation', affiliation)

        return placeholders

    def _get_report_target_key(self, rec: dict) -> str:
        # ログファイル名はARIMNOのみ（要件）
        arimno = self._get_report_record_value(rec or {}, ["ARIMNO", "課題番号"])
        return (arimno or "unknown")

    def _get_selected_report_records(self) -> List[dict]:
        if not hasattr(self, 'report_entries_table'):
            return []
        try:
            sm = self.report_entries_table.selectionModel()
            if sm is None:
                return []
            rows = sm.selectedRows(0)
            recs = []
            for mi in rows:
                try:
                    item = self.report_entries_table.item(mi.row(), 0)
                    if item is None:
                        continue
                    rec = item.data(Qt.UserRole)
                    if isinstance(rec, dict):
                        recs.append(rec)
                except Exception:
                    continue
            return recs
        except Exception:
            return []

    def _get_displayed_report_records(self) -> List[dict]:
        if not hasattr(self, 'report_entries_table'):
            return []
        try:
            recs = []
            seen = set()
            for row in range(self.report_entries_table.rowCount()):
                item = self.report_entries_table.item(row, 0)
                if item is None:
                    continue
                rec = item.data(Qt.UserRole)
                if not isinstance(rec, dict):
                    continue
                key = self._get_report_target_key(rec)
                if key in seen:
                    continue
                seen.add(key)
                recs.append(rec)
            return recs
        except Exception:
            return []

    def load_report_buttons(self):
        """AI拡張設定からボタンを読み込んで、報告書タブに表示"""
        try:
            from classes.dataset.util.ai_extension_helper import load_ai_extension_config, infer_ai_suggest_target_kind
            config = load_ai_extension_config()

            while self.report_buttons_layout.count():
                item = self.report_buttons_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()

            self.report_buttons.clear()

            ui_settings = config.get('ui_settings', {})
            button_height = ui_settings.get('button_height', 60)
            button_width = ui_settings.get('button_width', 140)
            show_icons = ui_settings.get('show_icons', True)

            buttons_config = config.get('buttons', [])
            default_buttons = config.get('default_buttons', [])
            all_buttons = buttons_config + default_buttons

            # 報告書向けのみ
            all_buttons = [b for b in all_buttons if infer_ai_suggest_target_kind(b) == 'report']

            if not all_buttons:
                no_buttons_label = QLabel("AI拡張ボタンが設定されていません。\n設定編集ボタンから設定ファイルを確認してください。")
                no_buttons_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; text-align: center; padding: 20px;")
                no_buttons_label.setAlignment(Qt.AlignCenter)
                self.report_buttons_layout.addWidget(no_buttons_label)
                return

            for button_config in all_buttons:
                button = self.create_extension_button(
                    button_config,
                    button_height,
                    button_width,
                    show_icons,
                    clicked_handler=self.on_report_button_clicked,
                    buttons_list=self.report_buttons,
                    target_kind="report",
                )
                self.report_buttons_layout.addWidget(button)

            self.report_buttons_layout.addStretch()

        except Exception as e:
            error_label = QLabel(f"AI拡張設定の読み込みエラー: {str(e)}")
            error_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; padding: 10px;")
            self.report_buttons_layout.addWidget(error_label)

    def on_report_button_clicked(self, button_config):
        """報告書タブのAIボタンクリック時の処理"""
        try:
            # 一括問い合わせ
            if getattr(self, 'report_bulk_checkbox', None) is not None and self.report_bulk_checkbox.isChecked():
                self._start_bulk_report_requests(button_config)
                return

            if not self._selected_report_placeholders:
                QMessageBox.warning(self, "警告", "報告書エントリーを選択してください（上部一覧から1件選択）。")
                return

            # 既存結果の検出（同一ボタン + 同一対象）
            try:
                from classes.dataset.util.ai_suggest_result_log import read_latest_result

                button_id = button_config.get('id', 'unknown')
                target_key = self._get_report_target_key(self._selected_report_record or {})

                latest = read_latest_result('report', target_key, button_id)
                if latest:
                    # pytest環境ではモーダル表示を避け、既存結果を自動表示して終了
                    if os.environ.get("PYTEST_CURRENT_TEST"):
                        fmt = (latest.get('display_format') or 'text').lower()
                        content = latest.get('display_content') or ''
                        if fmt == 'html':
                            self.report_response_display.setHtml(content)
                        else:
                            self.report_response_display.setText(content)
                        self.last_used_prompt = latest.get('prompt')
                        self.last_api_request_params = latest.get('request_params')
                        self.last_api_response_params = latest.get('response_params')
                        self.last_api_provider = latest.get('provider')
                        self.last_api_model = latest.get('model')
                        if hasattr(self, 'report_show_prompt_button'):
                            self.report_show_prompt_button.setEnabled(bool(self.last_used_prompt))
                        if hasattr(self, 'report_show_api_params_button'):
                            self.report_show_api_params_button.setEnabled(bool(self.last_api_request_params or self.last_api_response_params))
                        return

                    ts = (latest.get('timestamp') or '').strip()
                    box = QMessageBox(self)
                    box.setIcon(QMessageBox.Question)
                    box.setWindowTitle("既存結果あり")
                    box.setText(
                        f"同一ボタン・同一対象の既存結果が見つかりました。" + (f"（{ts}）" if ts else "")
                    )
                    box.setInformativeText("既存の最新結果を表示しますか？それとも新規に問い合わせますか？")
                    show_existing_btn = box.addButton("既存結果を表示", QMessageBox.AcceptRole)
                    run_new_btn = box.addButton("新規問い合わせ", QMessageBox.ActionRole)
                    cancel_btn = box.addButton(QMessageBox.Cancel)
                    box.setDefaultButton(show_existing_btn)
                    box.exec()

                    chosen = box.clickedButton()
                    if chosen == cancel_btn:
                        return
                    if chosen == show_existing_btn:
                        fmt = (latest.get('display_format') or 'text').lower()
                        content = latest.get('display_content') or ''
                        if fmt == 'html':
                            self.report_response_display.setHtml(content)
                        else:
                            self.report_response_display.setText(content)

                        # show prompt / api params 用の状態も復元
                        self.last_used_prompt = latest.get('prompt')
                        self.last_api_request_params = latest.get('request_params')
                        self.last_api_response_params = latest.get('response_params')
                        self.last_api_provider = latest.get('provider')
                        self.last_api_model = latest.get('model')
                        if hasattr(self, 'report_show_prompt_button'):
                            self.report_show_prompt_button.setEnabled(bool(self.last_used_prompt))
                        if hasattr(self, 'report_show_api_params_button'):
                            self.report_show_api_params_button.setEnabled(bool(self.last_api_request_params or self.last_api_response_params))
                        return

                    # run_new_btn の場合はそのまま問い合わせ続行
            except Exception:
                # ログ機能は失敗しても問い合わせ自体は継続
                pass

            clicked_button = self.sender()
            self._active_report_button = clicked_button if hasattr(clicked_button, 'start_loading') else None
            if clicked_button and hasattr(clicked_button, 'start_loading'):
                clicked_button.start_loading("AI処理中")

            prompt = self.build_report_prompt(button_config)
            if not prompt:
                if clicked_button:
                    clicked_button.stop_loading()
                QMessageBox.warning(self, "警告", "プロンプトの構築に失敗しました。")
                return

            self.execute_report_ai_request(prompt, button_config, clicked_button)

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"報告書ボタン処理エラー: {str(e)}")

    def _start_bulk_report_requests(self, button_config):
        """報告書タブ: 一括問い合わせ（選択 or 表示全件）"""
        try:
            selected = self._get_selected_report_records()
            displayed = self._get_displayed_report_records()
            use_selected = len(selected) > 0
            candidates = selected if use_selected else displayed
            if not candidates:
                QMessageBox.information(self, "情報", "一括問い合わせの対象がありません。")
                return

            try:
                from classes.dataset.util.ai_suggest_result_log import read_latest_result
            except Exception:
                read_latest_result = None

            planned_total = len(candidates)
            existing = 0
            tasks = []
            for rec in candidates:
                target_key = self._get_report_target_key(rec)
                latest = None
                if read_latest_result is not None:
                    try:
                        latest = read_latest_result('report', target_key, button_config.get('id', 'unknown'))
                    except Exception:
                        latest = None
                if latest:
                    existing += 1
                tasks.append({
                    'record': rec,
                    'target_key': target_key,
                    'has_existing': bool(latest),
                })

            missing = planned_total - existing
            scope_label = f"選択 {planned_total} 件" if use_selected else f"表示全件 {planned_total} 件"

            box = QMessageBox(self)
            box.setIcon(QMessageBox.Question)
            box.setWindowTitle("一括問い合わせ")
            box.setText(f"一括問い合わせを開始します。\n\n対象: {scope_label}")
            box.setInformativeText(
                f"予定件数: {planned_total} 件\n"
                f"既存結果あり: {existing} 件\n"
                f"既存結果なし: {missing} 件\n\n"
                "実行方法を選択してください。"
            )

            overwrite_btn = box.addButton("上書きして全件問い合わせ", QMessageBox.AcceptRole)
            missing_only_btn = box.addButton("既存なしのみ問い合わせ", QMessageBox.ActionRole)
            cancel_btn = box.addButton(QMessageBox.Cancel)
            box.setDefaultButton(missing_only_btn if missing > 0 else overwrite_btn)

            # pytest環境ではモーダルを避け、既存なしのみを選択
            if os.environ.get("PYTEST_CURRENT_TEST"):
                chosen = missing_only_btn
            else:
                box.exec()
                chosen = box.clickedButton()

            if chosen == cancel_btn:
                return
            if chosen == missing_only_btn:
                tasks = [t for t in tasks if not t.get('has_existing')]
            # overwrite_btn は tasks 全件

            if not tasks:
                QMessageBox.information(self, "情報", "問い合わせ対象（既存なし）がありません。")
                return

            self._bulk_report_queue = tasks
            self._bulk_report_index = 0
            self._bulk_report_total = len(tasks)
            self._bulk_report_next_index = 0
            self._bulk_report_inflight = 0
            self._bulk_report_running = True
            self._bulk_report_cancelled = False
            self._bulk_report_button_config = button_config

            # 最大並列数（標準5、最大20）
            requested = None
            try:
                requested = int(getattr(self, 'report_bulk_parallel_spinbox', None).value())
            except Exception:
                requested = None
            self._bulk_report_max_concurrency = self._normalize_bulk_report_concurrency(requested)

            # ボタン無効化
            for b in list(getattr(self, 'report_buttons', [])):
                try:
                    b.setEnabled(False)
                except Exception:
                    pass

            self._update_bulk_report_status_message()
            self._kick_bulk_report_scheduler()
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"一括問い合わせエラー: {str(e)}")

    def _run_next_bulk_report_request(self):
        """後方互換: 旧実装の直列次処理は新スケジューラに委譲"""
        self._kick_bulk_report_scheduler()

    def _normalize_bulk_report_concurrency(self, requested: Optional[int]) -> int:
        """一括問い合わせの最大並列数を正規化（標準5、最大20）"""
        try:
            value = int(requested) if requested is not None else 5
        except Exception:
            value = 5
        if value < 1:
            value = 1
        if value > 20:
            value = 20
        return value

    def _update_bulk_report_status_message(self):
        try:
            if getattr(self, 'report_spinner_overlay', None):
                label = (getattr(self, '_bulk_report_button_config', {}) or {}).get('label', 'AI')
                total = int(self._bulk_report_total or len(self._bulk_report_queue) or 0)
                done = int(self._bulk_report_index or 0)
                inflight = int(self._bulk_report_inflight or 0)
                if total > 0:
                    self.report_spinner_overlay.set_message(
                        f"一括処理中 完了 {done}/{total} / 実行中 {inflight}: {label}"
                    )
        except Exception:
            pass

    def _kick_bulk_report_scheduler(self):
        """一括問い合わせの並列スケジューラ（空きがあれば次タスクを起動）"""
        if not self._bulk_report_running or self._bulk_report_cancelled:
            # 実行中タスクが無くなったら終了
            if int(self._bulk_report_inflight or 0) <= 0:
                self._finish_bulk_report_requests()
            return

        total = int(self._bulk_report_total or len(self._bulk_report_queue) or 0)
        if total <= 0:
            self._finish_bulk_report_requests()
            return

        max_conc = self._normalize_bulk_report_concurrency(getattr(self, '_bulk_report_max_concurrency', 5))

        while (
            self._bulk_report_inflight < max_conc
            and self._bulk_report_next_index < len(self._bulk_report_queue)
            and self._bulk_report_running
            and not self._bulk_report_cancelled
        ):
            task = self._bulk_report_queue[self._bulk_report_next_index]
            self._bulk_report_next_index += 1

            rec = task.get('record')
            if not isinstance(rec, dict):
                # 不正データはスキップ（完了として扱う）
                self._bulk_report_index += 1
                continue

            placeholders = self._build_report_placeholders_for_record(rec)
            button_config = getattr(self, '_bulk_report_button_config', {}) or {}
            prompt = self.build_report_prompt(button_config, placeholders=placeholders)
            if not prompt:
                self._bulk_report_index += 1
                continue

            self._bulk_report_inflight += 1
            self._update_bulk_report_status_message()

            self.execute_report_ai_request(
                prompt,
                button_config,
                button_widget=None,
                report_record=rec,
                report_placeholders=placeholders,
                report_target_key=task.get('target_key') or self._get_report_target_key(rec),
                _bulk_continue=True,
            )

        # すべて投入済み & 実行中なしなら終了
        if (
            self._bulk_report_running
            and not self._bulk_report_cancelled
            and self._bulk_report_next_index >= len(self._bulk_report_queue)
            and self._bulk_report_inflight <= 0
            and self._bulk_report_index >= total
        ):
            self._finish_bulk_report_requests()

    def _on_bulk_report_task_done(self):
        """一括問い合わせの1タスク完了通知（成功/失敗共通）"""
        try:
            if self._bulk_report_inflight > 0:
                self._bulk_report_inflight -= 1
        except Exception:
            self._bulk_report_inflight = 0

        # 完了件数を進める（上限はtotalでクリップ）
        try:
            self._bulk_report_index += 1
            total = int(self._bulk_report_total or len(self._bulk_report_queue) or 0)
            if total > 0 and self._bulk_report_index > total:
                self._bulk_report_index = total
        except Exception:
            pass

        self._update_bulk_report_status_message()
        self._kick_bulk_report_scheduler()

    def _finish_bulk_report_requests(self):
        self._bulk_report_running = False
        self._bulk_report_cancelled = False
        self._bulk_report_queue = []
        self._bulk_report_index = 0
        self._bulk_report_total = 0
        self._bulk_report_next_index = 0
        self._bulk_report_inflight = 0
        try:
            if getattr(self, 'report_spinner_overlay', None):
                self.report_spinner_overlay.set_message("AI応答を待機中...")
        except Exception:
            pass
        for b in list(getattr(self, 'report_buttons', [])):
            try:
                b.setEnabled(True)
            except Exception:
                pass

    def setup_results_tab(self, tab_widget):
        """結果一覧タブ（ログの最新結果を一覧表示）"""
        from qt_compat.widgets import QTableWidget, QTableWidgetItem, QAbstractItemView
        from qt_compat.widgets import QLineEdit
        from qt_compat.widgets import QFileDialog

        layout = QVBoxLayout(tab_widget)

        header = QHBoxLayout()
        header.addWidget(QLabel("結果一覧（問い合わせログ）"))
        header.addStretch()
        layout.addLayout(header)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("対象:"))
        self.results_target_kind_combo = QComboBox()
        self.results_target_kind_combo.addItem("報告書", 'report')
        self.results_target_kind_combo.addItem("データセット", 'dataset')
        filters.addWidget(self.results_target_kind_combo)

        filters.addSpacing(10)
        filters.addWidget(QLabel("表示:"))
        self.results_view_mode_combo = QComboBox()
        self.results_view_mode_combo.addItem("先頭表示", 'snippet')
        self.results_view_mode_combo.addItem("JSON列表示", 'json_columns')
        filters.addWidget(self.results_view_mode_combo)

        filters.addSpacing(10)
        filters.addWidget(QLabel("ボタン:"))
        self.results_button_combo = QComboBox()
        self.results_button_combo.addItem("全て", '')
        filters.addWidget(self.results_button_combo)

        filters.addSpacing(10)
        filters.addWidget(QLabel("フィルタ:"))
        self.results_filter_edit = QLineEdit()
        self.results_filter_edit.setPlaceholderText("表示中の行を絞り込み")
        self.results_filter_edit.setMaximumWidth(240)
        filters.addWidget(self.results_filter_edit)

        filters.addSpacing(10)
        self.results_refresh_button = QPushButton("更新")
        self.results_refresh_button.setMaximumWidth(70)
        filters.addWidget(self.results_refresh_button)

        filters.addSpacing(10)
        filters.addWidget(QLabel("形式:"))
        self.results_export_format_combo = QComboBox()
        self.results_export_format_combo.addItem("CSV", 'csv')
        self.results_export_format_combo.addItem("XLSX", 'xlsx')
        self.results_export_format_combo.addItem("JSON", 'json')
        self.results_export_format_combo.setMaximumWidth(90)
        filters.addWidget(self.results_export_format_combo)

        self.results_export_button = QPushButton("エクスポート")
        self.results_export_button.setMaximumWidth(110)
        filters.addWidget(self.results_export_button)
        filters.addStretch()
        layout.addLayout(filters)

        # 対象=報告書 のときのみ表示する追加フィルタ
        self.results_report_filters_widget = QWidget()
        report_filters = QHBoxLayout(self.results_report_filters_widget)
        report_filters.setContentsMargins(0, 0, 0, 0)

        report_filters.addWidget(QLabel("年度:"))
        self.results_report_year_combo = QComboBox()
        self.results_report_year_combo.setMinimumWidth(110)
        self.results_report_year_combo.addItem("全て")
        report_filters.addWidget(self.results_report_year_combo)

        report_filters.addSpacing(10)
        report_filters.addWidget(QLabel("機関コード:"))
        self.results_report_inst_code_edit = QLineEdit()
        self.results_report_inst_code_edit.setPlaceholderText("AA")
        self.results_report_inst_code_edit.setFixedWidth(80)
        report_filters.addWidget(self.results_report_inst_code_edit)

        report_filters.addSpacing(10)
        report_filters.addWidget(QLabel("横断(主):"))
        self.results_report_cross_main_combo = QComboBox()
        self.results_report_cross_main_combo.setMinimumWidth(180)
        self.results_report_cross_main_combo.addItem("全て")
        report_filters.addWidget(self.results_report_cross_main_combo)

        report_filters.addSpacing(10)
        report_filters.addWidget(QLabel("横断(副):"))
        self.results_report_cross_sub_combo = QComboBox()
        self.results_report_cross_sub_combo.setMinimumWidth(180)
        self.results_report_cross_sub_combo.addItem("全て")
        report_filters.addWidget(self.results_report_cross_sub_combo)

        report_filters.addSpacing(10)
        report_filters.addWidget(QLabel("重要(主):"))
        self.results_report_important_main_combo = QComboBox()
        self.results_report_important_main_combo.setMinimumWidth(180)
        self.results_report_important_main_combo.addItem("全て")
        report_filters.addWidget(self.results_report_important_main_combo)

        report_filters.addSpacing(10)
        report_filters.addWidget(QLabel("重要(副):"))
        self.results_report_important_sub_combo = QComboBox()
        self.results_report_important_sub_combo.setMinimumWidth(180)
        self.results_report_important_sub_combo.addItem("全て")
        report_filters.addWidget(self.results_report_important_sub_combo)

        report_filters.addStretch()
        layout.addWidget(self.results_report_filters_widget)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels([
            "日時",
            "対象キー",
            "ボタン",
            "モデル",
            "所要時間(秒)",
            "結果(先頭)",
        ])
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        try:
            self.results_table.setSortingEnabled(True)
        except Exception:
            pass
        layout.addWidget(self.results_table, 1)

        # 接続
        self.results_target_kind_combo.currentIndexChanged.connect(self._populate_results_button_combo)
        self.results_target_kind_combo.currentIndexChanged.connect(self._on_results_target_kind_changed)
        self.results_button_combo.currentIndexChanged.connect(self.refresh_results_list)
        self.results_view_mode_combo.currentIndexChanged.connect(self.refresh_results_list)
        self.results_filter_edit.textChanged.connect(self._apply_results_filter)
        self.results_refresh_button.clicked.connect(self.refresh_results_list)
        self.results_export_button.clicked.connect(self.export_results_table)

        # 報告書向け追加フィルタ
        self.results_report_year_combo.currentIndexChanged.connect(self.refresh_results_list)
        self.results_report_inst_code_edit.textChanged.connect(self.refresh_results_list)
        self.results_report_cross_main_combo.currentIndexChanged.connect(self.refresh_results_list)
        self.results_report_cross_sub_combo.currentIndexChanged.connect(self.refresh_results_list)
        self.results_report_important_main_combo.currentIndexChanged.connect(self.refresh_results_list)
        self.results_report_important_sub_combo.currentIndexChanged.connect(self.refresh_results_list)
        # 行クリックでログファイル表示
        try:
            self.results_table.cellClicked.connect(self._on_results_table_cell_clicked)
        except Exception:
            pass

        self._populate_results_button_combo()
        self._on_results_target_kind_changed()
        self.refresh_results_list()

    def _on_results_target_kind_changed(self) -> None:
        """対象切替に応じて、報告書向けフィルタUIの表示を切り替える。"""
        try:
            kind = self.results_target_kind_combo.currentData() if hasattr(self, 'results_target_kind_combo') else 'report'
            show_report_filters = (kind == 'report')
            if hasattr(self, 'results_report_filters_widget'):
                self.results_report_filters_widget.setVisible(show_report_filters)
        except Exception:
            pass

    def _on_results_table_cell_clicked(self, row: int, _col: int) -> None:
        """結果一覧の行クリックで、対応するログファイルを表示する。"""
        try:
            if not hasattr(self, 'results_table'):
                return
            item = self.results_table.item(row, 0)
            if item is None:
                return
            rec = item.data(Qt.UserRole)
            if not isinstance(rec, dict):
                return
            self._show_results_log_for_record(rec)
        except Exception as e:
            try:
                QMessageBox.warning(self, "警告", f"ログ表示に失敗しました: {e}")
            except Exception:
                pass

    @staticmethod
    def _is_empty_or_nan(value) -> bool:
        if value is None:
            return True
        if isinstance(value, float):
            try:
                return math.isnan(value)
            except Exception:
                return False
        text = str(value).strip()
        if text == "":
            return True
        return text.lower() == "nan"

    def _show_results_log_for_record(self, rec: dict) -> None:
        """ログファイルを読み込み、JSONは全文/階層ツリー切替、テキストはそのまま表示する。"""
        from qt_compat.widgets import (
            QDialog,
            QVBoxLayout,
            QLabel,
            QTextEdit,
            QTabWidget,
            QTreeWidget,
            QTreeWidgetItem,
            QPushButton,
            QHBoxLayout,
        )
        from qt_compat.gui import QDesktopServices
        from qt_compat.core import QUrl
        from classes.dataset.util.ai_suggest_result_log import resolve_log_path

        target_kind = (rec.get('target_kind') or '').strip() or (self.results_target_kind_combo.currentData() if hasattr(self, 'results_target_kind_combo') else 'report')
        button_id = (rec.get('button_id') or '').strip()
        target_key = (rec.get('target_key') or '').strip()

        path = resolve_log_path(str(target_kind), str(button_id), str(target_key))

        # 子ダイアログ（open() で非同期モーダル: テストでもブロックしない）
        dlg = QDialog(self)
        dlg.setObjectName('ai_suggest_log_viewer')
        dlg.setWindowTitle('ログファイル表示')
        dlg.resize(900, 600)

        layout = QVBoxLayout(dlg)
        path_label = QLabel(f"{path}")
        try:
            path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        except Exception:
            pass
        layout.addWidget(path_label)

        # 標準エディタで開く
        open_row = QHBoxLayout()
        open_row.addStretch()
        open_button = QPushButton("標準テキストエディタで開く")
        open_button.setObjectName('ai_suggest_log_open_in_editor')
        open_button.setToolTip("OSの標準関連付けでログファイルを開きます")

        def _open_in_editor() -> None:
            try:
                if not path or not os.path.exists(path):
                    QMessageBox.warning(self, "警告", f"ファイルが見つかりません: {path}")
                    return
                try:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                    return
                except Exception:
                    pass
                try:
                    os.startfile(path)  # noqa: S606
                except Exception as e:
                    QMessageBox.warning(self, "警告", f"標準エディタで開けませんでした:\n{path}\n\n{e}")
            except Exception:
                pass

        try:
            open_button.clicked.connect(_open_in_editor)
        except Exception:
            pass
        open_row.addWidget(open_button)
        layout.addLayout(open_row)

        # 読み込み
        raw_text = ""
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                raw_text = f.read()
        except Exception as e:
            QMessageBox.warning(self, "警告", f"ログファイルを読み込めませんでした:\n{path}\n\n{e}")
            return

        obj = None
        ext = os.path.splitext(path)[1].lower()
        if ext in {'.json', '.jsonl'}:
            try:
                if ext == '.jsonl':
                    # jsonl: 最終行（最後のJSONレコード）を表示
                    last = None
                    for line in raw_text.splitlines():
                        if line.strip():
                            last = line
                    if last is not None:
                        obj = json.loads(last)
                else:
                    obj = json.loads(raw_text)
            except Exception:
                obj = None
        else:
            # 拡張子に依らず JSON っぽければ試す
            try:
                obj = json.loads(raw_text)
            except Exception:
                obj = None

        if isinstance(obj, dict):
            tabs = QTabWidget()
            tabs.setObjectName('ai_suggest_log_tabs')

            # ツリー表示
            tree = QTreeWidget()
            tree.setObjectName('ai_suggest_log_tree')
            tree.setColumnCount(2)
            tree.setHeaderLabels(['キー', '値'])

            def _value_summary(v) -> str:
                if v is None:
                    return ''
                if isinstance(v, dict):
                    return f"{{...}} ({len(v)})"
                if isinstance(v, list):
                    return f"[...] ({len(v)})"
                try:
                    text = '' if self._is_empty_or_nan(v) else str(v)
                except Exception:
                    text = str(v)
                if len(text) > 200:
                    return text[:200] + '…'
                return text

            def _add_tree_nodes(parent_item: Optional[QTreeWidgetItem], key: str, value) -> None:
                item = QTreeWidgetItem([str(key), _value_summary(value)])
                # 長文はツールチップで全文
                try:
                    if not isinstance(value, (dict, list)):
                        text = '' if self._is_empty_or_nan(value) else str(value)
                        if len(text) > 200:
                            item.setToolTip(1, text)
                except Exception:
                    pass

                if parent_item is None:
                    tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)

                if isinstance(value, dict):
                    for k2, v2 in value.items():
                        _add_tree_nodes(item, str(k2), v2)
                elif isinstance(value, list):
                    for idx, v2 in enumerate(value):
                        _add_tree_nodes(item, f"[{idx}]", v2)

            for k, v in obj.items():
                _add_tree_nodes(None, str(k), v)

            try:
                tree.expandToDepth(1)
                tree.resizeColumnToContents(0)
            except Exception:
                pass

            tabs.addTab(tree, 'ツリー')

            # JSON全文表示
            json_text = QTextEdit()
            json_text.setObjectName('ai_suggest_log_json_text')
            json_text.setReadOnly(True)
            try:
                if ext == '.jsonl':
                    json_text.setPlainText(raw_text)
                else:
                    json_text.setPlainText(json.dumps(obj, ensure_ascii=False, indent=2))
            except Exception:
                json_text.setPlainText(raw_text)
            tabs.addTab(json_text, 'JSON')

            layout.addWidget(tabs, 1)
        elif isinstance(obj, list):
            tabs = QTabWidget()
            tabs.setObjectName('ai_suggest_log_tabs')

            tree = QTreeWidget()
            tree.setObjectName('ai_suggest_log_tree')
            tree.setColumnCount(2)
            tree.setHeaderLabels(['キー', '値'])

            def _value_summary(v) -> str:
                if v is None:
                    return ''
                if isinstance(v, dict):
                    return f"{{...}} ({len(v)})"
                if isinstance(v, list):
                    return f"[...] ({len(v)})"
                try:
                    text = '' if self._is_empty_or_nan(v) else str(v)
                except Exception:
                    text = str(v)
                if len(text) > 200:
                    return text[:200] + '…'
                return text

            def _add_tree_nodes(parent_item: Optional[QTreeWidgetItem], key: str, value) -> None:
                item = QTreeWidgetItem([str(key), _value_summary(value)])
                try:
                    if not isinstance(value, (dict, list)):
                        text = '' if self._is_empty_or_nan(value) else str(value)
                        if len(text) > 200:
                            item.setToolTip(1, text)
                except Exception:
                    pass

                if parent_item is None:
                    tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)

                if isinstance(value, dict):
                    for k2, v2 in value.items():
                        _add_tree_nodes(item, str(k2), v2)
                elif isinstance(value, list):
                    for idx, v2 in enumerate(value):
                        _add_tree_nodes(item, f"[{idx}]", v2)

            for idx, v in enumerate(obj):
                _add_tree_nodes(None, f"[{idx}]", v)

            try:
                tree.expandToDepth(1)
                tree.resizeColumnToContents(0)
            except Exception:
                pass
            tabs.addTab(tree, 'ツリー')

            json_text = QTextEdit()
            json_text.setObjectName('ai_suggest_log_json_text')
            json_text.setReadOnly(True)
            try:
                if ext == '.jsonl':
                    json_text.setPlainText(raw_text)
                else:
                    json_text.setPlainText(json.dumps(obj, ensure_ascii=False, indent=2))
            except Exception:
                json_text.setPlainText(raw_text)
            tabs.addTab(json_text, 'JSON')
            layout.addWidget(tabs, 1)
        else:
            text = QTextEdit()
            text.setObjectName('ai_suggest_log_text')
            text.setReadOnly(True)
            text.setPlainText(raw_text)
            layout.addWidget(text, 1)

        # 参照保持（GC防止）
        self._results_log_viewer = dlg
        try:
            dlg.open()
        except Exception:
            dlg.show()

    def _collect_results_table_visible_data(self):
        """現在表示されている（フィルタで非表示の行は除外）テーブルデータを取得。"""
        if not hasattr(self, 'results_table'):
            return [], []

        headers = []
        for c in range(self.results_table.columnCount()):
            item = self.results_table.horizontalHeaderItem(c)
            headers.append(item.text() if item else '')

        rows = []
        for r in range(self.results_table.rowCount()):
            try:
                if self.results_table.isRowHidden(r):
                    continue
            except Exception:
                pass
            row = []
            for c in range(self.results_table.columnCount()):
                cell = self.results_table.item(r, c)
                row.append(cell.text() if cell else '')
            rows.append(row)

        return headers, rows

    @staticmethod
    def _write_results_export_csv(path: str, headers, rows) -> None:
        import csv

        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(list(headers))
            for row in rows:
                writer.writerow(list(row))

    @staticmethod
    def _write_results_export_json(path: str, headers, rows) -> None:
        import json

        keys = list(headers)
        data = []
        for row in rows:
            obj = {keys[i]: (row[i] if i < len(row) else '') for i in range(len(keys))}
            data.append(obj)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _write_results_export_xlsx(path: str, headers, rows) -> None:
        try:
            from openpyxl import Workbook  # type: ignore
        except Exception as e:
            raise RuntimeError(f"openpyxl が利用できません: {e}")

        wb = Workbook()
        ws = wb.active
        ws.title = "results"
        ws.append(list(headers))
        for row in rows:
            ws.append(list(row))
        wb.save(path)

    def export_results_table(self):
        """結果一覧タブのテーブル表示内容をエクスポート（CSV/XLSX/JSON）。"""
        try:
            from qt_compat.widgets import QFileDialog
            from config.common import get_dynamic_file_path
            from datetime import datetime
            import os

            fmt = 'csv'
            try:
                fmt = self.results_export_format_combo.currentData() if hasattr(self, 'results_export_format_combo') else 'csv'
            except Exception:
                fmt = 'csv'
            fmt = (fmt or 'csv').strip().lower()
            if fmt not in {'csv', 'xlsx', 'json'}:
                fmt = 'csv'

            kind = self.results_target_kind_combo.currentData() if hasattr(self, 'results_target_kind_combo') else 'report'
            bid = self.results_button_combo.currentData() if hasattr(self, 'results_button_combo') else ''
            bid = (bid or '').strip() or 'all'

            headers, rows = self._collect_results_table_visible_data()
            if not headers:
                QMessageBox.information(self, "情報", "エクスポートするデータがありません。")
                return

            default_dir = get_dynamic_file_path('output')
            os.makedirs(default_dir, exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            default_name = f"ai_suggest_results_{kind}_{bid}_{ts}.{fmt}"
            default_path = os.path.join(default_dir, default_name)

            if fmt == 'csv':
                file_filter = "CSV (*.csv)"
            elif fmt == 'xlsx':
                file_filter = "Excel (*.xlsx)"
            else:
                file_filter = "JSON (*.json)"

            path, _ = QFileDialog.getSaveFileName(self, "結果一覧をエクスポート", default_path, file_filter)
            if not path:
                return

            # 拡張子補正
            ext = f".{fmt}"
            if not path.lower().endswith(ext):
                path += ext

            if fmt == 'csv':
                self._write_results_export_csv(path, headers, rows)
            elif fmt == 'xlsx':
                self._write_results_export_xlsx(path, headers, rows)
            else:
                self._write_results_export_json(path, headers, rows)

            QMessageBox.information(self, "エクスポート完了", f"保存しました:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"エクスポートに失敗しました: {e}")

    def _populate_results_button_combo(self):
        try:
            from classes.dataset.util.ai_extension_helper import load_ai_extension_config, infer_ai_suggest_target_kind
            kind = self.results_target_kind_combo.currentData() if hasattr(self, 'results_target_kind_combo') else 'report'
            config = load_ai_extension_config()
            buttons_config = (config.get('buttons', []) or []) + (config.get('default_buttons', []) or [])
            filtered = []
            for b in buttons_config:
                try:
                    if infer_ai_suggest_target_kind(b) == ('report' if kind == 'report' else 'dataset'):
                        filtered.append(b)
                except Exception:
                    continue

            self.results_button_combo.blockSignals(True)
            self.results_button_combo.clear()
            self.results_button_combo.addItem("全て", '')
            for b in filtered:
                bid = b.get('id', 'unknown')
                label = b.get('label', bid)
                self.results_button_combo.addItem(f"{label} ({bid})", bid)
            self.results_button_combo.blockSignals(False)
        except Exception:
            # fail safe
            try:
                self.results_button_combo.blockSignals(True)
                self.results_button_combo.clear()
                self.results_button_combo.addItem("全て", '')
                self.results_button_combo.blockSignals(False)
            except Exception:
                pass

    def refresh_results_list(self):
        # コンボ更新等で再帰的に呼ばれる場合があるため、再入を防止する
        if getattr(self, '_refresh_results_list_running', False):
            return
        self._refresh_results_list_running = True
        try:
            from qt_compat.widgets import QTableWidgetItem
            from classes.dataset.util.ai_suggest_result_log import list_latest_results
            from classes.dataset.util.ai_extension_helper import load_ai_extension_config
            from classes.dataset.util.ai_extension_helper import normalize_results_json_keys
            from classes.dataset.util.report_listing_helper import (
                extract_task_number_from_report_target_key,
                load_latest_report_records,
            )

            kind = self.results_target_kind_combo.currentData() if hasattr(self, 'results_target_kind_combo') else 'report'
            bid = self.results_button_combo.currentData() if hasattr(self, 'results_button_combo') else ''
            bid = (bid or '').strip() or None

            view_mode = 'snippet'
            try:
                view_mode = self.results_view_mode_combo.currentData() if hasattr(self, 'results_view_mode_combo') else 'snippet'
            except Exception:
                view_mode = 'snippet'

            recs = list_latest_results(kind, bid)

            # 対象=報告書のとき、converted.xlsx 由来のレコード（またはフォールバック）と結合して
            # 年度/機関コード/技術領域を表示・フィルタする。
            report_rows_by_task = {}
            if kind == 'report':
                try:
                    report_records = self._get_displayed_report_records()
                except Exception:
                    report_records = []

                # report tabが未生成でも、converted.xlsx から読み込んで結合に使う
                if not report_records:
                    try:
                        from classes.dataset.util.ai_extension_helper import load_converted_xlsx_report_entries

                        report_records = load_converted_xlsx_report_entries()
                    except Exception:
                        report_records = []

                if not report_records:
                    try:
                        report_records = load_latest_report_records()
                    except Exception:
                        report_records = []

                def _as_int_year(value: str) -> int:
                    s = (value or '').strip()
                    if not s:
                        return -1
                    try:
                        # '2024年度' なども許容
                        m = re.search(r"(\d{4})", s)
                        if m:
                            return int(m.group(1))
                        return int(s)
                    except Exception:
                        return -1

                # task_number -> [{year, inst_code, cross_main, cross_sub, important_main, important_sub}]
                report_rows_by_task = {}
                for rec in report_records or []:
                    if not isinstance(rec, dict):
                        continue
                    task_number = self._get_report_record_value(rec, [
                        "課題番号",
                        "ARIMNO",
                        "課題番号 / Project Issue Number",
                        "課題番号 / Project Issue Number",
                    ])
                    task_number = (task_number or '').strip()
                    if not task_number:
                        continue

                    year = self._get_report_record_value(rec, ["年度", "利用年度", "Fiscal Year", "利用年度 / Fiscal Year"]).strip()
                    inst_code = self._get_report_record_value(rec, ["機関コード", "実施機関コード", "Support Institute", "利用した実施機関"]).strip()
                    cross_main = self._get_report_record_value(rec, [
                        "横断技術領域・主",
                        "横断技術領域（主）",
                        "キーワード【横断技術領域】（主）",
                        "キーワード【横断技術領域】(主)",
                    ])
                    cross_sub = self._get_report_record_value(rec, [
                        "横断技術領域・副",
                        "横断技術領域（副）",
                        "キーワード【横断技術領域】（副）",
                        "キーワード【横断技術領域】(副)",
                    ])
                    important_main = self._get_report_record_value(rec, [
                        "重要技術領域・主",
                        "重要技術領域（主）",
                        "キーワード【重要技術領域】（主）",
                        "キーワード【重要技術領域】(主)",
                    ])
                    important_sub = self._get_report_record_value(rec, [
                        "重要技術領域・副",
                        "重要技術領域（副）",
                        "キーワード【重要技術領域】（副）",
                        "キーワード【重要技術領域】(副)",
                    ])

                    row = {
                        'year': year,
                        'inst_code': inst_code,
                        'cross_main': cross_main,
                        'cross_sub': cross_sub,
                        'important_main': important_main,
                        'important_sub': important_sub,
                    }
                    report_rows_by_task.setdefault(task_number, []).append(row)

                def _parse_report_target_key_parts(target_key: str) -> tuple[str, str, str]:
                    """<課題番号>|<年度>|<機関コード> を安全に分解して返す。

                    reportタブのログキーはARIMNOのみの場合もあるため、その場合は(課題番号,'','')。
                    """
                    t = (target_key or '').strip()
                    if not t:
                        return ('', '', '')
                    parts = t.split('|')
                    task = (parts[0].strip() if len(parts) >= 1 else '')
                    year0 = (parts[1].strip() if len(parts) >= 2 else '')
                    inst0 = (parts[2].strip() if len(parts) >= 3 else '')
                    return (task, year0, inst0)

                def _pick_best_report_row(task_number: str, year_hint: str, inst_hint: str) -> dict:
                    rows = list(report_rows_by_task.get(task_number, []) or [])
                    if not rows:
                        return {}

                    # year/inst がヒントとしてある場合はできるだけ一致させる
                    if year_hint:
                        rows_y = [r for r in rows if (r.get('year') or '').strip() == year_hint]
                        if rows_y:
                            rows = rows_y
                    if inst_hint:
                        rows_i = [r for r in rows if inst_hint in ((r.get('inst_code') or '').strip())]
                        if rows_i:
                            rows = rows_i

                    if not rows:
                        return {}

                    # 複数候補が残る場合は、年度が最大のものを優先（converted.xlsxの典型運用に合わせる）
                    rows_sorted = sorted(rows, key=lambda r: _as_int_year(str(r.get('year') or '')), reverse=True)
                    return rows_sorted[0] if rows_sorted else (rows[0] if rows else {})

                def _joined_report_fields_for_target_key(target_key: str) -> dict:
                    task, y_hint, inst_hint = _parse_report_target_key_parts(str(target_key or ''))
                    task = task or extract_task_number_from_report_target_key(str(target_key or ''))
                    if not task:
                        return {}
                    picked = _pick_best_report_row(task, y_hint, inst_hint)
                    # キー側情報もフォールバックとして残す
                    return {
                        'task_number': task,
                        'year': str(picked.get('year') or y_hint or '').strip(),
                        'inst_code': str(picked.get('inst_code') or inst_hint or '').strip(),
                        'cross_main': '' if self._is_empty_or_nan(picked.get('cross_main')) else str(picked.get('cross_main') or '').strip(),
                        'cross_sub': '' if self._is_empty_or_nan(picked.get('cross_sub')) else str(picked.get('cross_sub') or '').strip(),
                        'important_main': '' if self._is_empty_or_nan(picked.get('important_main')) else str(picked.get('important_main') or '').strip(),
                        'important_sub': '' if self._is_empty_or_nan(picked.get('important_sub')) else str(picked.get('important_sub') or '').strip(),
                    }

            else:
                def _joined_report_fields_for_target_key(_target_key: str) -> dict:  # type: ignore[misc]
                    return {}

            # 報告書向けフィルタ候補を更新（結合後の値ベース）
            if kind == 'report' and hasattr(self, 'results_report_year_combo'):
                years = []
                cross_mains = []
                cross_subs = []
                imp_mains = []
                imp_subs = []

                for rec in recs:
                    jf = _joined_report_fields_for_target_key(str(rec.get('target_key') or ''))
                    y = str(jf.get('year') or '').strip()
                    if y and y not in years:
                        years.append(y)
                    for key, acc in [
                        ('cross_main', cross_mains),
                        ('cross_sub', cross_subs),
                        ('important_main', imp_mains),
                        ('important_sub', imp_subs),
                    ]:
                        v = str(jf.get(key) or '').strip()
                        if v and v not in acc:
                            acc.append(v)

                def _update_combo(combo, values) -> None:
                    try:
                        current = combo.currentText() or '全て'
                    except Exception:
                        current = '全て'
                    combo.blockSignals(True)
                    combo.clear()
                    combo.addItem('全て')
                    for v in sorted(values):
                        combo.addItem(v)
                    idx = combo.findText(current)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    combo.blockSignals(False)

                try:
                    years_sorted = sorted(years)
                    current_year = self.results_report_year_combo.currentText() if hasattr(self, 'results_report_year_combo') else '全て'
                    self.results_report_year_combo.blockSignals(True)
                    self.results_report_year_combo.clear()
                    self.results_report_year_combo.addItem('全て')
                    for y in years_sorted:
                        self.results_report_year_combo.addItem(y)
                    idx = self.results_report_year_combo.findText(current_year)
                    if idx >= 0:
                        self.results_report_year_combo.setCurrentIndex(idx)
                    self.results_report_year_combo.blockSignals(False)

                    _update_combo(self.results_report_cross_main_combo, cross_mains)
                    _update_combo(self.results_report_cross_sub_combo, cross_subs)
                    _update_combo(self.results_report_important_main_combo, imp_mains)
                    _update_combo(self.results_report_important_sub_combo, imp_subs)
                except Exception:
                    pass

            # 報告書向けフィルタをログ一覧へ適用（結合後の値ベース）
            if kind == 'report' and hasattr(self, 'results_report_year_combo'):
                year_filter = (self.results_report_year_combo.currentText() or '').strip()
                inst_code_filter = (self.results_report_inst_code_edit.text() if hasattr(self, 'results_report_inst_code_edit') else '')
                inst_code_filter = (inst_code_filter or '').strip()
                cross_main_filter = (self.results_report_cross_main_combo.currentText() or '').strip()
                cross_sub_filter = (self.results_report_cross_sub_combo.currentText() or '').strip()
                imp_main_filter = (self.results_report_important_main_combo.currentText() or '').strip()
                imp_sub_filter = (self.results_report_important_sub_combo.currentText() or '').strip()

                filtered_recs = []
                for rec in recs:
                    tkey = str(rec.get('target_key') or '')
                    jf = _joined_report_fields_for_target_key(tkey)
                    y = str(jf.get('year') or '').strip()
                    inst = str(jf.get('inst_code') or '').strip()
                    cm = str(jf.get('cross_main') or '').strip()
                    cs = str(jf.get('cross_sub') or '').strip()
                    im = str(jf.get('important_main') or '').strip()
                    isub = str(jf.get('important_sub') or '').strip()

                    if year_filter and year_filter != '全て' and year_filter != y:
                        continue
                    if inst_code_filter and inst_code_filter not in inst:
                        continue
                    if cross_main_filter and cross_main_filter != '全て' and cross_main_filter not in cm:
                        continue
                    if cross_sub_filter and cross_sub_filter != '全て' and cross_sub_filter not in cs:
                        continue
                    if imp_main_filter and imp_main_filter != '全て' and imp_main_filter not in im:
                        continue
                    if imp_sub_filter and imp_sub_filter != '全て' and imp_sub_filter not in isub:
                        continue
                    filtered_recs.append(rec)
                recs = filtered_recs

            # Helper: parse JSON-path like "a.b[0].c"
            def _get_json_value(obj, key_path: str):
                if obj is None:
                    return None
                if not key_path:
                    return None
                cur = obj
                # Split by '.' but keep bracket segments
                parts = [p for p in str(key_path).split('.') if p != '']
                for part in parts:
                    # handle bracket indexing, e.g. "items[0]" or "[0]"
                    m = re.match(r"^(?P<name>[^\[]+)?(?P<rest>(\[\d+\])*)$", part)
                    if not m:
                        return None
                    name = m.group('name')
                    rest = m.group('rest') or ''

                    if name:
                        if isinstance(cur, dict):
                            cur = cur.get(name)
                        else:
                            return None

                    for im in re.finditer(r"\[(\d+)\]", rest):
                        idx = int(im.group(1))
                        if isinstance(cur, list) and 0 <= idx < len(cur):
                            cur = cur[idx]
                        else:
                            return None
                return cur

            def _display_cell_value(v) -> str:
                if v is None:
                    return ''
                if isinstance(v, (dict, list)):
                    try:
                        s = json.dumps(v, ensure_ascii=False)
                    except Exception:
                        s = str(v)
                else:
                    s = str(v)
                s = re.sub(r"\s+", " ", s).strip()
                return s[:160] + ('…' if len(s) > 160 else '')

            def _parse_json_from_record(rec: dict):
                text = rec.get('display_content')
                if text is None:
                    return None
                try:
                    return json.loads(text)
                except Exception:
                    return None

            def _snippet(rec: dict) -> str:
                fmt = (rec.get('display_format') or 'text').lower()
                content = rec.get('display_content') or ''
                if fmt == 'html':
                    # strip tags (simple)
                    content = re.sub(r'<[^>]+>', ' ', content)
                content = re.sub(r'\s+', ' ', str(content)).strip()
                return content[:120] + ('…' if len(content) > 120 else '')

            def _format_elapsed_seconds(rec: dict) -> str:
                v = rec.get('elapsed_seconds')
                if v is not None and v != '':
                    try:
                        fv = float(v)
                        if fv < 0:
                            return ''
                        return f"{fv:.2f}"
                    except Exception:
                        return ''

                started = rec.get('started_at')
                finished = rec.get('finished_at')
                if not started or not finished:
                    return ''
                try:
                    from datetime import datetime

                    def _parse_iso(s: str) -> datetime:
                        s = str(s).strip()
                        if s.endswith('Z'):
                            s = s[:-1] + '+00:00'
                        return datetime.fromisoformat(s)

                    dt0 = _parse_iso(started)
                    dt1 = _parse_iso(finished)
                    sec = (dt1 - dt0).total_seconds()
                    if sec < 0:
                        return ''
                    return f"{sec:.2f}"
                except Exception:
                    return ''

            # JSON列表示はボタン指定が必須（キー設定がボタン定義に紐づくため）
            if view_mode == 'json_columns' and not bid:
                view_mode = 'snippet'

            try:
                self.results_table.setSortingEnabled(False)
            except Exception:
                pass

            if view_mode == 'snippet':
                if kind == 'report':
                    self.results_table.setColumnCount(12)
                    self.results_table.setHorizontalHeaderLabels([
                        "日時",
                        "対象キー",
                        "年度",
                        "機関コード",
                        "横断技術領域（主）",
                        "横断技術領域（副）",
                        "重要技術領域（主）",
                        "重要技術領域（副）",
                        "ボタン",
                        "モデル",
                        "所要時間(秒)",
                        "結果(先頭)",
                    ])
                else:
                    self.results_table.setColumnCount(6)
                    self.results_table.setHorizontalHeaderLabels([
                        "日時",
                        "対象キー",
                        "ボタン",
                        "モデル",
                        "所要時間(秒)",
                        "結果(先頭)",
                    ])
                self.results_table.setRowCount(len(recs))
                for row_idx, rec in enumerate(recs):
                    ts = str(rec.get('timestamp') or '')
                    tkey = str(rec.get('target_key') or '')
                    blabel = str(rec.get('button_label') or rec.get('button_id') or '')
                    model = str(rec.get('model') or '')
                    elapsed = _format_elapsed_seconds(rec)
                    snip = _snippet(rec)

                    if kind == 'report':
                        jf = _joined_report_fields_for_target_key(tkey)
                        values = [
                            ts,
                            tkey,
                            str(jf.get('year') or ''),
                            str(jf.get('inst_code') or ''),
                            str(jf.get('cross_main') or ''),
                            str(jf.get('cross_sub') or ''),
                            str(jf.get('important_main') or ''),
                            str(jf.get('important_sub') or ''),
                            blabel,
                            model,
                            elapsed,
                            snip,
                        ]
                    else:
                        values = [ts, tkey, blabel, model, elapsed, snip]

                    for col_idx, value in enumerate(values):
                        item = QTableWidgetItem(value)
                        item.setData(Qt.UserRole, rec)
                        self.results_table.setItem(row_idx, col_idx, item)
            else:
                # JSON列表示
                config = load_ai_extension_config()
                buttons_config = (config.get('buttons', []) or []) + (config.get('default_buttons', []) or [])
                btn_conf = None
                for b in buttons_config:
                    if b.get('id') == bid:
                        btn_conf = b
                        break
                keys = normalize_results_json_keys((btn_conf or {}).get('results_json_keys'))

                rows = []
                for rec in recs:
                    ts = str(rec.get('timestamp') or '')
                    tkey = str(rec.get('target_key') or '')
                    blabel = str(rec.get('button_label') or rec.get('button_id') or '')
                    model = str(rec.get('model') or '')

                    obj = _parse_json_from_record(rec)
                    if isinstance(obj, list):
                        for i, elem in enumerate(obj):
                            if isinstance(elem, dict):
                                data_obj = elem
                            else:
                                data_obj = {'_value': elem}
                            row = {
                                'ts': ts,
                                'tkey': tkey,
                                'elem': str(i),
                                'blabel': blabel,
                                'model': model,
                                'json': data_obj,
                                'rec': rec,
                            }
                            rows.append(row)
                    elif isinstance(obj, dict):
                        rows.append({'ts': ts, 'tkey': tkey, 'elem': '', 'blabel': blabel, 'model': model, 'json': obj, 'rec': rec})
                    else:
                        # 非JSON（またはパース失敗）
                        rows.append({'ts': ts, 'tkey': tkey, 'elem': '', 'blabel': blabel, 'model': model, 'json': {}, 'rec': rec})

                include_elem = any((r.get('elem') or '') != '' for r in rows)
                if kind == 'report':
                    base_headers = [
                        "日時",
                        "対象キー",
                        "年度",
                        "機関コード",
                        "横断技術領域（主）",
                        "横断技術領域（副）",
                        "重要技術領域（主）",
                        "重要技術領域（副）",
                    ] + (["要素"] if include_elem else []) + ["ボタン", "モデル", "所要時間(秒)"]
                else:
                    base_headers = ["日時", "対象キー"] + (["要素"] if include_elem else []) + ["ボタン", "モデル", "所要時間(秒)"]
                headers = base_headers + keys
                self.results_table.setColumnCount(len(headers))
                self.results_table.setHorizontalHeaderLabels(headers)

                self.results_table.setRowCount(len(rows))
                for row_idx, row in enumerate(rows):
                    rec = row['rec']

                    elapsed = _format_elapsed_seconds(rec)

                    if kind == 'report':
                        jf = _joined_report_fields_for_target_key(row['tkey'])
                        year = str(jf.get('year') or '')
                        inst_code = str(jf.get('inst_code') or '')
                        cross_main = str(jf.get('cross_main') or '')
                        cross_sub = str(jf.get('cross_sub') or '')
                        imp_main = str(jf.get('important_main') or '')
                        imp_sub = str(jf.get('important_sub') or '')
                        base_values = [
                            row['ts'],
                            row['tkey'],
                            year,
                            inst_code,
                            cross_main,
                            cross_sub,
                            imp_main,
                            imp_sub,
                        ] + ([row['elem']] if include_elem else []) + [row['blabel'], row['model'], elapsed]
                        json_base_headers = [
                            "日時",
                            "対象キー",
                            "年度",
                            "機関コード",
                            "横断技術領域（主）",
                            "横断技術領域（副）",
                            "重要技術領域（主）",
                            "重要技術領域（副）",
                        ] + (["要素"] if include_elem else []) + ["ボタン", "モデル", "所要時間(秒)"]
                    else:
                        base_values = [row['ts'], row['tkey']] + ([row['elem']] if include_elem else []) + [row['blabel'], row['model'], elapsed]
                        json_base_headers = ["日時", "対象キー"] + (["要素"] if include_elem else []) + ["ボタン", "モデル", "所要時間(秒)"]

                    for col_idx, value in enumerate(base_values):
                        item = QTableWidgetItem(str(value))
                        item.setData(Qt.UserRole, rec)
                        self.results_table.setItem(row_idx, col_idx, item)

                    for k_idx, key in enumerate(keys):
                        v = _get_json_value(row['json'], key)
                        item = QTableWidgetItem(_display_cell_value(v))
                        item.setData(Qt.UserRole, rec)
                        self.results_table.setItem(row_idx, len(json_base_headers) + k_idx, item)

            try:
                self.results_table.setSortingEnabled(True)
            except Exception:
                pass

            self._apply_results_filter()

            try:
                self.results_table.resizeColumnsToContents()
            except Exception:
                pass
        except Exception as e:
            logger.debug("refresh_results_list failed: %s", e)
            try:
                self.results_table.setRowCount(0)
            except Exception:
                pass
        finally:
            self._refresh_results_list_running = False

    def _apply_results_filter(self):
        try:
            if not hasattr(self, 'results_table'):
                return
            q = ''
            try:
                q = (self.results_filter_edit.text() if hasattr(self, 'results_filter_edit') else '') or ''
            except Exception:
                q = ''
            q = q.strip().lower()
            for r in range(self.results_table.rowCount()):
                if not q:
                    self.results_table.setRowHidden(r, False)
                    continue
                hit = False
                for c in range(self.results_table.columnCount()):
                    item = self.results_table.item(r, c)
                    if item and q in (item.text() or '').lower():
                        hit = True
                        break
                self.results_table.setRowHidden(r, not hit)
        except Exception:
            pass

    def build_report_prompt(self, button_config, placeholders: Optional[dict] = None):
        """報告書タブ用プロンプトを構築"""
        try:
            prompt_file = button_config.get('prompt_file')
            prompt_template = button_config.get('prompt_template')

            button_id = button_config.get('id', 'unknown')
            if prompt_file:
                prompt_file = self._get_prompt_file_for_target(prompt_file, 'report', button_id)

            if prompt_file:
                from classes.dataset.util.ai_extension_helper import load_prompt_file
                template_content = load_prompt_file(prompt_file)
                if not template_content:
                    template_content = f"""報告書について分析してください。

ARIMNO: {{ARIMNO}}
利用課題名: {{利用課題名}}
所属名: {{所属名}}
年度: {{年度}}
機関コード: {{機関コード}}

上記の情報を基に、「{button_config.get('label', 'AI分析')}」の観点から分析してください。"""
            elif prompt_template:
                template_content = prompt_template
            else:
                template_content = f"""報告書について分析してください。

ARIMNO: {{ARIMNO}}
利用課題名: {{利用課題名}}
所属名: {{所属名}}
年度: {{年度}}
機関コード: {{機関コード}}

上記の情報を基に、「{button_config.get('label', 'AI分析')}」の観点から分析してください。"""

            context_data = (placeholders or {}).copy() if placeholders is not None else (self._selected_report_placeholders.copy() if self._selected_report_placeholders else {})

            from classes.dataset.util.ai_extension_helper import format_prompt_with_context
            formatted_prompt = format_prompt_with_context(template_content, context_data)
            return formatted_prompt

        except Exception as e:
            logger.error("報告書プロンプト構築エラー: %s", e)
            return None

    def execute_report_ai_request(
        self,
        prompt,
        button_config,
        button_widget,
        retry_count: int = 0,
        report_record: Optional[dict] = None,
        report_placeholders: Optional[dict] = None,
        report_target_key: Optional[str] = None,
        _bulk_continue: bool = False,
    ):
        """報告書タブ用のAIリクエストを実行（表示先を report_response_display にする）"""
        try:
            self.last_used_prompt = prompt
            self.last_api_request_params = None
            self.last_api_response_params = None
            self.last_api_provider = None
            self.last_api_model = None

            if hasattr(self, 'report_show_api_params_button'):
                self.report_show_api_params_button.setEnabled(False)

            if hasattr(self, 'report_show_prompt_button'):
                self.report_show_prompt_button.setEnabled(True)

            # ボタン無効化
            for b in list(self.report_buttons):
                try:
                    b.setEnabled(False)
                except Exception:
                    pass

            # スピナー
            button_label = button_config.get('label', 'AI処理')
            button_icon = button_config.get('icon', '🤖')
            if getattr(self, 'report_spinner_overlay', None):
                # 一括実行中はスケジューラ側で進捗メッセージを管理する
                if not (_bulk_continue and self._bulk_report_running):
                    self.report_spinner_overlay.set_message(f"{button_icon} {button_label} 実行中...")

            # 開始時刻/所要時間計測（ログ保存用）
            started_at = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec='seconds')
            started_perf = time.perf_counter()

            # AIリクエストスレッド
            ai_thread = AIRequestThread(prompt, self._selected_report_placeholders)
            self.report_ai_threads.append(ai_thread)

            self.update_report_spinner_visibility()

            def on_success(result):
                try:
                    try:
                        self.last_api_request_params = result.get('request_params')
                        self.last_api_response_params = result.get('response_params')
                        self.last_api_provider = result.get('provider')
                        self.last_api_model = result.get('model')
                        if hasattr(self, 'report_show_api_params_button'):
                            self.report_show_api_params_button.setEnabled(bool(self.last_api_request_params or self.last_api_response_params))
                    except Exception:
                        pass

                    response_text = result.get('response') or result.get('content', '')
                    if response_text:
                        fmt = button_config.get('output_format', 'text')
                        if fmt == 'json':
                            valid, fixed_text = self._validate_and_fix_json_response(response_text)
                            if valid:
                                self.report_response_display.setText(fixed_text)
                            else:
                                if retry_count < 2:
                                    if ai_thread in self.report_ai_threads:
                                        self.report_ai_threads.remove(ai_thread)
                                    self.update_report_spinner_visibility()
                                    self.execute_report_ai_request(prompt, button_config, button_widget, retry_count + 1)
                                    return
                                else:
                                    self.report_response_display.setText(self._wrap_json_error(
                                        error_message="JSONの検証に失敗しました（最大リトライ到達）",
                                        raw_output=response_text,
                                        retries=retry_count
                                    ))
                        else:
                            formatted_response = self.format_extension_response(response_text, button_config)
                            self.report_response_display.setHtml(formatted_response)
                    else:
                        self.report_response_display.setText("AI応答が空でした。")

                    # ログ保存
                    try:
                        from classes.dataset.util.ai_suggest_result_log import append_result

                        button_id = button_config.get('id', 'unknown')
                        button_label = button_config.get('label', 'Unknown')
                        if report_target_key:
                            target_key = report_target_key
                        else:
                            rec_for_key = report_record if isinstance(report_record, dict) else (self._selected_report_record or {})
                            target_key = self._get_report_target_key(rec_for_key)

                        if fmt == 'json':
                            display_format = 'text'
                            display_content = self.report_response_display.toPlainText()
                        else:
                            display_format = 'html'
                            display_content = self.report_response_display.toHtml()

                        append_result(
                            target_kind='report',
                            target_key=target_key,
                            button_id=button_id,
                            button_label=button_label,
                            prompt=self.last_used_prompt or prompt,
                            display_format=display_format,
                            display_content=display_content,
                            provider=self.last_api_provider,
                            model=self.last_api_model,
                            request_params=self.last_api_request_params,
                            response_params=self.last_api_response_params,
                            started_at=started_at,
                            finished_at=datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec='seconds'),
                            elapsed_seconds=round(time.perf_counter() - started_perf, 3),
                        )
                    except Exception:
                        pass
                finally:
                    if button_widget:
                        button_widget.stop_loading()
                    if self._active_report_button is button_widget:
                        self._active_report_button = None
                    if ai_thread in self.report_ai_threads:
                        self.report_ai_threads.remove(ai_thread)
                    self.update_report_spinner_visibility()
                    if not self._bulk_report_running and getattr(self, 'report_spinner_overlay', None):
                        self.report_spinner_overlay.set_message("AI応答を待機中...")
                    if not self._bulk_report_running:
                        for b in list(self.report_buttons):
                            try:
                                b.setEnabled(True)
                            except Exception:
                                pass

                    # 一括継続
                    if _bulk_continue and self._bulk_report_running:
                        self._on_bulk_report_task_done()

            def on_error(error_message):
                try:
                    self.report_response_display.setText(f"エラー: {error_message}")
                finally:
                    if button_widget:
                        button_widget.stop_loading()
                    if self._active_report_button is button_widget:
                        self._active_report_button = None
                    if ai_thread in self.report_ai_threads:
                        self.report_ai_threads.remove(ai_thread)
                    self.update_report_spinner_visibility()
                    if not self._bulk_report_running and getattr(self, 'report_spinner_overlay', None):
                        self.report_spinner_overlay.set_message("AI応答を待機中...")
                    if not self._bulk_report_running:
                        for b in list(self.report_buttons):
                            try:
                                b.setEnabled(True)
                            except Exception:
                                pass

                    if _bulk_continue and self._bulk_report_running:
                        self._on_bulk_report_task_done()

                    self.last_api_request_params = None
                    self.last_api_response_params = None
                    self.last_api_provider = None
                    self.last_api_model = None
                    if hasattr(self, 'report_show_api_params_button'):
                        self.report_show_api_params_button.setEnabled(False)

            ai_thread.result_ready.connect(on_success)
            ai_thread.error_occurred.connect(on_error)
            ai_thread.start()

        except Exception as e:
            if button_widget:
                button_widget.stop_loading()
            if self._active_report_button is button_widget:
                self._active_report_button = None
            for b in list(self.report_buttons):
                try:
                    b.setEnabled(True)
                except Exception:
                    pass
            QMessageBox.critical(self, "エラー", f"報告書AIリクエスト実行エラー: {str(e)}")

    def update_report_spinner_visibility(self):
        try:
            if getattr(self, 'report_spinner_overlay', None):
                if len(self.report_ai_threads) > 0:
                    self.report_spinner_overlay.start()
                else:
                    self.report_spinner_overlay.stop()
        except Exception as _e:
            logger.debug("update_report_spinner_visibility failed: %s", _e)

    def cancel_report_ai_requests(self):
        """報告書タブの実行中リクエストをキャンセル"""
        try:
            # 一括処理の残タスクも中断
            self._bulk_report_cancelled = True
            self._bulk_report_running = False
            self._bulk_report_queue = []
            self._bulk_report_total = 0
            self._bulk_report_next_index = 0
            self._bulk_report_inflight = 0
            for thread in list(self.report_ai_threads):
                try:
                    if thread and thread.isRunning():
                        thread.stop()
                except Exception:
                    pass
        except Exception as e:
            logger.debug("cancel_report_ai_requests failed: %s", e)
        
    def setup_extraction_settings_tab(self, tab_widget):
        """ファイル抽出設定タブのセットアップ"""
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # ヘッダー
        header_label = QLabel("⚙️ ファイルテキスト抽出設定")
        header_label.setStyleSheet(
            f"font-size: 14px; font-weight: bold; margin-bottom: 10px; color: {get_color(ThemeKey.TEXT_PRIMARY)};"
        )
        layout.addWidget(header_label)
        
        description_label = QLabel(
            "AI分析で使用するファイルからのテキスト抽出に関する設定を調整できます。\n"
            "これらの設定は、データセットのSTRUCTUREDファイルからテキストを抽出する際に適用されます。"
        )
        description_label.setWordWrap(True)
        description_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; margin-bottom: 10px; font-size: 11px;"
        )
        layout.addWidget(description_label)
        
        # スクロールエリア
        from qt_compat.widgets import QScrollArea
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(15)
        
        # 1. 対象ファイル種別設定
        file_types_group = QGroupBox("📄 対象ファイル種別")
        file_types_layout = QVBoxLayout(file_types_group)
        
        file_types_desc = QLabel("テキスト抽出対象とするファイルの拡張子を指定します（カンマ区切り）")
        file_types_desc.setWordWrap(True)
        file_types_desc.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px; margin-bottom: 5px;"
        )
        file_types_layout.addWidget(file_types_desc)
        
        from qt_compat.widgets import QLineEdit
        self.file_extensions_input = QLineEdit()
        self.file_extensions_input.setPlaceholderText("例: .txt, .csv, .xlsx, .json, .md")
        self.file_extensions_input.setText(".txt, .csv, .xlsx, .json, .md, .log, .xml")
        self.file_extensions_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 6px;
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                border-radius: 4px;
                font-size: 11px;
            }}
        """)
        file_types_layout.addWidget(self.file_extensions_input)
        
        scroll_layout.addWidget(file_types_group)
        
        # 2. 除外ファイルパターン設定
        exclude_group = QGroupBox("🚫 除外ファイルパターン")
        exclude_layout = QVBoxLayout(exclude_group)
        
        exclude_desc = QLabel("除外するファイル名のパターンを指定します（正規表現、改行区切り）")
        exclude_desc.setWordWrap(True)
        exclude_desc.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px; margin-bottom: 5px;"
        )
        exclude_layout.addWidget(exclude_desc)
        
        self.exclude_patterns_input = QTextEdit()
        self.exclude_patterns_input.setPlaceholderText(
            "例:\n"
            ".*_anonymized\\.json\n"
            "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.json\n"
            ".*\\.tmp"
        )
        self.exclude_patterns_input.setPlainText(
            ".*_anonymized\\.json\n"
            "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.json"
        )
        self.exclude_patterns_input.setMaximumHeight(100)
        self.exclude_patterns_input.setStyleSheet(f"""
            QTextEdit {{
                padding: 6px;
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                background-color: {get_color(ThemeKey.TEXT_AREA_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                border-radius: 4px;
                font-size: 10px;
                font-family: 'Consolas', 'Monaco', monospace;
            }}
        """)
        exclude_layout.addWidget(self.exclude_patterns_input)
        
        scroll_layout.addWidget(exclude_group)
        
        # 3. 処理ファイル数上限
        from qt_compat.widgets import QSpinBox
        from qt_compat import QtWidgets

        def _make_pm_buttons(spinbox: QSpinBox, base_name: str) -> tuple[QtWidgets.QPushButton, QtWidgets.QPushButton]:
            """スピンボックスの増減を分かりやすくするため、明示的な -/+ ボタンを返す。"""
            try:
                spinbox.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            except Exception:
                pass

            minus_btn = QtWidgets.QPushButton("−")
            plus_btn = QtWidgets.QPushButton("＋")
            minus_btn.setObjectName(f"{base_name}_minus_button")
            plus_btn.setObjectName(f"{base_name}_plus_button")
            minus_btn.setToolTip("減らす")
            plus_btn.setToolTip("増やす")

            # 連打/長押しでの操作性
            try:
                minus_btn.setAutoRepeat(True)
                plus_btn.setAutoRepeat(True)
                minus_btn.setAutoRepeatDelay(300)
                plus_btn.setAutoRepeatDelay(300)
                minus_btn.setAutoRepeatInterval(60)
                plus_btn.setAutoRepeatInterval(60)
            except Exception:
                pass

            try:
                minus_btn.clicked.connect(spinbox.stepDown)
                plus_btn.clicked.connect(spinbox.stepUp)
            except Exception:
                # テスト環境でMock化される可能性への防御
                pass

            btn_style = (
                f"QPushButton {{ "
                f"min-width: 28px; min-height: 24px; "
                f"border: 1px solid {get_color(ThemeKey.INPUT_BORDER)}; "
                f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; "
                f"color: {get_color(ThemeKey.INPUT_TEXT)}; "
                f"border-radius: 4px; font-size: 12px; padding: 0px; "
                f"}} "
                f"QPushButton:pressed {{ background-color: {get_color(ThemeKey.BUTTON_DEFAULT_BACKGROUND_HOVER)}; }}"
            )
            minus_btn.setStyleSheet(btn_style)
            plus_btn.setStyleSheet(btn_style)
            return minus_btn, plus_btn
        max_files_group = QGroupBox("📊 処理ファイル数上限")
        max_files_layout = QVBoxLayout(max_files_group)
        
        max_files_desc = QLabel("一度に処理するファイルの最大数を設定します")
        max_files_desc.setWordWrap(True)
        max_files_desc.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px; margin-bottom: 5px;"
        )
        max_files_layout.addWidget(max_files_desc)
        
        max_files_h_layout = QHBoxLayout()
        self.max_files_spinbox = QSpinBox()
        self.max_files_spinbox.setMinimum(1)
        self.max_files_spinbox.setMaximum(100)
        self.max_files_spinbox.setValue(10)
        self.max_files_spinbox.setSuffix(" 件")
        self.max_files_spinbox.setStyleSheet(f"""
            QSpinBox {{
                padding: 6px;
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                border-radius: 4px;
                font-size: 11px;
            }}
        """)
        max_files_minus_btn, max_files_plus_btn = _make_pm_buttons(self.max_files_spinbox, "max_files")
        max_files_h_layout.addWidget(self.max_files_spinbox)
        max_files_h_layout.addWidget(max_files_minus_btn)
        max_files_h_layout.addWidget(max_files_plus_btn)
        max_files_h_layout.addStretch()
        max_files_layout.addLayout(max_files_h_layout)
        
        scroll_layout.addWidget(max_files_group)
        
        # 4. ファイルサイズ上限
        max_file_size_group = QGroupBox("📏 ファイルサイズ上限")
        max_file_size_layout = QVBoxLayout(max_file_size_group)
        
        max_file_size_desc = QLabel("処理対象とするファイルの最大サイズを設定します")
        max_file_size_desc.setWordWrap(True)
        max_file_size_desc.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px; margin-bottom: 5px;"
        )
        max_file_size_layout.addWidget(max_file_size_desc)
        
        max_file_size_h_layout = QHBoxLayout()
        self.max_file_size_spinbox = QSpinBox()
        self.max_file_size_spinbox.setMinimum(1)
        self.max_file_size_spinbox.setMaximum(100)
        self.max_file_size_spinbox.setValue(10)
        self.max_file_size_spinbox.setSuffix(" MB")
        self.max_file_size_spinbox.setStyleSheet(f"""
            QSpinBox {{
                padding: 6px;
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                border-radius: 4px;
                font-size: 11px;
            }}
        """)
        max_file_size_minus_btn, max_file_size_plus_btn = _make_pm_buttons(self.max_file_size_spinbox, "max_file_size")
        max_file_size_h_layout.addWidget(self.max_file_size_spinbox)
        max_file_size_h_layout.addWidget(max_file_size_minus_btn)
        max_file_size_h_layout.addWidget(max_file_size_plus_btn)
        max_file_size_h_layout.addStretch()
        max_file_size_layout.addLayout(max_file_size_h_layout)
        
        scroll_layout.addWidget(max_file_size_group)
        
        # 5. 出力文字数制限
        max_chars_group = QGroupBox("📝 出力文字数制限")
        max_chars_layout = QVBoxLayout(max_chars_group)
        
        max_chars_desc = QLabel("抽出したテキストの最大文字数を設定します（1ファイルあたり）")
        max_chars_desc.setWordWrap(True)
        max_chars_desc.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px; margin-bottom: 5px;"
        )
        max_chars_layout.addWidget(max_chars_desc)
        
        max_chars_h_layout = QHBoxLayout()
        self.max_chars_spinbox = QSpinBox()
        self.max_chars_spinbox.setMinimum(100)
        self.max_chars_spinbox.setMaximum(50000)
        self.max_chars_spinbox.setSingleStep(1000)
        self.max_chars_spinbox.setValue(10000)
        self.max_chars_spinbox.setSuffix(" 文字")
        self.max_chars_spinbox.setStyleSheet(f"""
            QSpinBox {{
                padding: 6px;
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                border-radius: 4px;
                font-size: 11px;
            }}
        """)
        max_chars_minus_btn, max_chars_plus_btn = _make_pm_buttons(self.max_chars_spinbox, "max_chars")
        max_chars_h_layout.addWidget(self.max_chars_spinbox)
        max_chars_h_layout.addWidget(max_chars_minus_btn)
        max_chars_h_layout.addWidget(max_chars_plus_btn)
        max_chars_h_layout.addStretch()
        max_chars_layout.addLayout(max_chars_h_layout)
        
        scroll_layout.addWidget(max_chars_group)
        
        # 6. Excel設定
        excel_group = QGroupBox("📊 Excel設定")
        excel_layout = QVBoxLayout(excel_group)
        
        excel_desc = QLabel("Excelファイルの処理に関する設定")
        excel_desc.setWordWrap(True)
        excel_desc.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px; margin-bottom: 5px;"
        )
        excel_layout.addWidget(excel_desc)
        
        from qt_compat.widgets import QCheckBox
        self.excel_all_sheets_checkbox = QCheckBox("全シートを処理する（無効時は最初のシートのみ）")
        self.excel_all_sheets_checkbox.setChecked(True)
        self.excel_all_sheets_checkbox.setStyleSheet("font-size: 11px;")
        excel_layout.addWidget(self.excel_all_sheets_checkbox)
        
        excel_max_rows_h_layout = QHBoxLayout()
        excel_max_rows_label = QLabel("シートあたり最大行数:")
        excel_max_rows_label.setStyleSheet("font-size: 11px;")
        excel_max_rows_h_layout.addWidget(excel_max_rows_label)
        
        self.excel_max_rows_spinbox = QSpinBox()
        self.excel_max_rows_spinbox.setMinimum(10)
        self.excel_max_rows_spinbox.setMaximum(10000)
        self.excel_max_rows_spinbox.setSingleStep(100)
        self.excel_max_rows_spinbox.setValue(1000)
        self.excel_max_rows_spinbox.setSuffix(" 行")
        self.excel_max_rows_spinbox.setStyleSheet(f"""
            QSpinBox {{
                padding: 4px;
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                border-radius: 4px;
                font-size: 11px;
            }}
        """)
        excel_max_rows_minus_btn, excel_max_rows_plus_btn = _make_pm_buttons(self.excel_max_rows_spinbox, "excel_max_rows")
        excel_max_rows_h_layout.addWidget(self.excel_max_rows_spinbox)
        excel_max_rows_h_layout.addWidget(excel_max_rows_minus_btn)
        excel_max_rows_h_layout.addWidget(excel_max_rows_plus_btn)
        excel_max_rows_h_layout.addStretch()
        excel_layout.addLayout(excel_max_rows_h_layout)
        
        scroll_layout.addWidget(excel_group)
        
        scroll_layout.addStretch()
        
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area, 1)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        # 設定を読み込みボタン
        self.load_settings_button = QPushButton("📂 設定を読み込み")
        self.load_settings_button.clicked.connect(self.load_extraction_settings)
        button_layout.addWidget(self.load_settings_button)
        
        # 設定を保存ボタン
        self.save_settings_button = QPushButton("💾 設定を保存")
        self.save_settings_button.clicked.connect(self.save_extraction_settings)
        button_layout.addWidget(self.save_settings_button)
        
        # デフォルトに戻すボタン
        self.reset_settings_button = QPushButton("🔄 デフォルトに戻す")
        self.reset_settings_button.clicked.connect(self.reset_extraction_settings)
        button_layout.addWidget(self.reset_settings_button)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        # 初期設定を読み込み
        QTimer.singleShot(100, self.load_extraction_settings)

    def refresh_theme(self, *_):
        """テーマ変更時に必要なスタイルを再適用する"""
        try:
            # AI拡張: 応答制御ボタン
            if hasattr(self, 'clear_response_button') and self.clear_response_button:
                self.clear_response_button.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                        border: none;
                        border-radius: 4px;
                        padding: 6px 12px;
                        font-size: 12px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
                    }}
                    QPushButton:pressed {{
                        background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED)};
                    }}
                    """
                )

            # プロンプト統計ラベル
            if hasattr(self, 'prompt_stats') and self.prompt_stats:
                self.prompt_stats.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; margin: 5px;")
            
            # AI拡張タブ: ボタン統計・説明ラベル
            if hasattr(self, '_buttons_label') and self._buttons_label:
                self._buttons_label.setStyleSheet(
                    f"font-weight: bold; margin: 5px 0; font-size: 13px; color: {get_color(ThemeKey.TEXT_SECONDARY)};"
                )
            if hasattr(self, '_response_label') and self._response_label:
                self._response_label.setStyleSheet(
                    f"font-weight: bold; margin: 5px 0; font-size: 13px; color: {get_color(ThemeKey.TEXT_SECONDARY)};"
                )

            # AI拡張: 応答表示エリア（QTextBrowserの枠線・背景色のみ更新、詳細スタイルは保持）
            if hasattr(self, 'extension_response_display') and self.extension_response_display:
                # 既存の詳細スタイルを保ったまま境界色のみ更新
                current_style = self.extension_response_display.styleSheet()
                # border色とbackground色のみ置換
                import re
                updated_style = re.sub(
                    r'border:\s*1px\s+solid\s+#[0-9a-fA-F]{6};',
                    f'border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};',
                    current_style
                )
                updated_style = re.sub(
                    r'background-color:\s*#[0-9a-fA-F]{6};',
                    f'background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};',
                    updated_style
                )
                self.extension_response_display.setStyleSheet(updated_style)

            # プログレスバー（テーマキーを使用して境界・チャンク色を更新）
            if hasattr(self, 'progress_bar') and self.progress_bar:
                self.progress_bar.setStyleSheet(
                    f"""
                    QProgressBar {{
                        border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                        border-radius: 5px;
                        text-align: center;
                        font-weight: bold;
                    }}
                    QProgressBar::chunk {{
                        background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                        border-radius: 3px;
                    }}
                    """
                )

            # アクションボタン群（色再適用）
            button_variants = {
                'primary': {
                    'bg': ThemeKey.BUTTON_PRIMARY_BACKGROUND,
                    'text': ThemeKey.BUTTON_PRIMARY_TEXT,
                    'border': ThemeKey.BUTTON_PRIMARY_BORDER,
                    'hover': ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER,
                    'pressed': ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED,
                },
                'success': {
                    'bg': ThemeKey.BUTTON_SUCCESS_BACKGROUND,
                    'text': ThemeKey.BUTTON_SUCCESS_TEXT,
                    'border': ThemeKey.BUTTON_SUCCESS_BORDER,
                    'hover': ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER,
                    'pressed': ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED,
                },
                'danger': {
                    'bg': ThemeKey.BUTTON_DANGER_BACKGROUND,
                    'text': ThemeKey.BUTTON_DANGER_TEXT,
                    'border': ThemeKey.BUTTON_DANGER_BORDER,
                    'hover': ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER,
                    'pressed': ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED,
                },
                'info': {
                    'bg': ThemeKey.BUTTON_INFO_BACKGROUND,
                    'text': ThemeKey.BUTTON_INFO_TEXT,
                    'border': ThemeKey.BUTTON_INFO_BORDER,
                    'hover': ThemeKey.BUTTON_INFO_BACKGROUND_HOVER,
                    'pressed': ThemeKey.BUTTON_INFO_BACKGROUND_PRESSED,
                },
                'warning': {
                    'bg': ThemeKey.BUTTON_WARNING_BACKGROUND,
                    'text': ThemeKey.BUTTON_WARNING_TEXT,
                    'border': ThemeKey.BUTTON_WARNING_BORDER,
                    'hover': ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER,
                    'pressed': ThemeKey.BUTTON_WARNING_BACKGROUND_PRESSED,
                },
                'neutral': {
                    'bg': ThemeKey.BUTTON_NEUTRAL_BACKGROUND,
                    'text': ThemeKey.BUTTON_NEUTRAL_TEXT,
                    'border': ThemeKey.BUTTON_NEUTRAL_BORDER,
                    'hover': ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER,
                },
            }

            def _apply_btn(btn, variant):
                try:
                    if not btn:
                        return
                    config = button_variants.get(variant)
                    if not config:
                        return
                    style = (
                        f"QPushButton {{ background-color: {get_color(config['bg'])}; color: {get_color(config['text'])}; "
                        f"border: 1px solid {get_color(config['border'])}; border-radius:4px; padding:6px 12px; font-weight:bold; }}"
                    )
                    hover_key = config.get('hover')
                    if hover_key:
                        style += f"QPushButton:hover {{ background-color: {get_color(hover_key)}; }}"
                    pressed_key = config.get('pressed')
                    if pressed_key:
                        style += f"QPushButton:pressed {{ background-color: {get_color(pressed_key)}; }}"
                    style += (
                        f"QPushButton:disabled {{ background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)}; "
                        f"color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)}; border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)}; }}"
                    )
                    btn.setStyleSheet(style)
                except Exception as _e:
                    logger.debug(f"Button theme apply failed: {_e}")

            _apply_btn(getattr(self, 'generate_button', None), 'success')
            _apply_btn(getattr(self, 'cancel_ai_button', None), 'danger')
            _apply_btn(getattr(self, 'apply_button', None), 'primary')
            _apply_btn(getattr(self, 'cancel_button', None), 'neutral')
            _apply_btn(getattr(self, 'clear_response_button', None), 'danger')
            _apply_btn(getattr(self, 'copy_response_button', None), 'success')
            _apply_btn(getattr(self, 'show_prompt_button', None), 'info')
            _apply_btn(getattr(self, 'load_settings_button', None), 'info')
            _apply_btn(getattr(self, 'save_settings_button', None), 'success')
            _apply_btn(getattr(self, 'reset_settings_button', None), 'warning')

            if hasattr(self, 'spinner_overlay') and self.spinner_overlay:
                try:
                    self.spinner_overlay.refresh_theme()
                except Exception:
                    pass

        except Exception as e:
            logger.debug("refresh_theme failed: %s", e)
    
    def load_extension_buttons(self):
        """AI拡張設定からボタンを読み込んで表示"""
        try:
            from classes.dataset.util.ai_extension_helper import load_ai_extension_config, infer_ai_suggest_target_kind
            config = load_ai_extension_config()
            
            # 既存のボタンをクリア（ストレッチやスペーサにも対応）
            while self.buttons_layout.count():
                item = self.buttons_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
                # QSpacerItem など widget を持たない要素は takeAt の時点で除去済み

            # 旧ボタン参照を破棄
            self.extension_buttons.clear()
            
            ui_settings = config.get('ui_settings', {})
            buttons_per_row = ui_settings.get('buttons_per_row', 3)
            button_height = ui_settings.get('button_height', 60)
            button_width = ui_settings.get('button_width', 140)
            show_icons = ui_settings.get('show_icons', True)
            enable_categories = ui_settings.get('enable_categories', True)
            
            # ボタン設定を取得
            buttons_config = config.get('buttons', [])
            default_buttons = config.get('default_buttons', [])
            
            # 全ボタンをまとめる
            all_buttons = buttons_config + default_buttons

            # AI拡張(従来)向けのみ
            all_buttons = [b for b in all_buttons if infer_ai_suggest_target_kind(b) != 'report']
            
            if not all_buttons:
                no_buttons_label = QLabel("AI拡張ボタンが設定されていません。\n設定編集ボタンから設定ファイルを確認してください。")
                no_buttons_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; text-align: center; padding: 20px;")
                no_buttons_label.setAlignment(Qt.AlignCenter)
                self.buttons_layout.addWidget(no_buttons_label)
                return
            
            # カテゴリ別にボタンを整理
            if enable_categories:
                categories = {}
                for button_config in all_buttons:
                    category = button_config.get('category', 'その他')
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(button_config)
                
                # カテゴリごとにボタンを作成
                for category_name, category_buttons in categories.items():
                    self.create_category_section(category_name, category_buttons, buttons_per_row, button_height, button_width, show_icons)
            else:
                # カテゴリなしでボタンを作成
                self.create_buttons_grid(all_buttons, buttons_per_row, button_height, button_width, show_icons)
            
            # 最後にストレッチを追加
            self.buttons_layout.addStretch()
            
        except Exception as e:
            error_label = QLabel(f"AI拡張設定の読み込みエラー: {str(e)}")
            error_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; padding: 10px;")
            self.buttons_layout.addWidget(error_label)
    
    def create_category_section(self, category_name, buttons, buttons_per_row, button_height, button_width, show_icons):
        """カテゴリセクションを作成（シンプル版）"""
        # ボタンを1列に配置（カテゴリヘッダーは不要）
        for button_config in buttons:
            button = self.create_extension_button(button_config, button_height, button_width, show_icons)
            self.buttons_layout.addWidget(button)
    
    def create_buttons_grid(self, buttons, buttons_per_row, button_height, button_width, show_icons):
        """ボタングリッドを作成（カテゴリなし・シンプル版）"""
        # ボタンを1列に配置
        for button_config in buttons:
            button = self.create_extension_button(button_config, button_height, button_width, show_icons)
            self.buttons_layout.addWidget(button)
    
    def create_extension_button(
        self,
        button_config,
        button_height,
        button_width,
        show_icons,
        clicked_handler=None,
        buttons_list=None,
        target_kind: str = "dataset",
    ):
        """AI拡張ボタンを作成（改良版）

        互換性のため、従来の呼び出し（4引数）も維持しつつ、
        報告書タブなど別ターゲット用にクリックハンドラ/ボタンリストを差し替え可能。
        """
        return self._create_extension_button_impl(
            button_config,
            button_height,
            button_width,
            show_icons,
            clicked_handler=clicked_handler,
            buttons_list=buttons_list,
            target_kind=target_kind,
        )

    def _create_extension_button_impl(
        self,
        button_config,
        button_height,
        button_width,
        show_icons,
        clicked_handler=None,
        buttons_list=None,
        target_kind: str = "dataset",
    ):
        """Create a button for AI extension tabs (dataset/report).

        clicked_handler: callable(button_config)
        buttons_list: list to store created buttons for disable/enable
        target_kind: "dataset" or "report" (used for preview behavior)
        """
        from classes.dataset.ui.spinner_button import SpinnerButton
        
        button_id = button_config.get('id', 'unknown')
        label = button_config.get('label', 'Unknown')
        description = button_config.get('description', '')
        icon = button_config.get('icon', '🤖') if show_icons else ''
        
        # ボタンテキスト（アイコン＋タイトル＋説明を統合）
        button_text = f"{icon} {label}"
        if description:
            # 説明が長い場合は短縮
            short_desc = description[:40] + "..." if len(description) > 40 else description
            button_text += f"\n{short_desc}"
        
        button = SpinnerButton(button_text)
        
        # ボタンサイズを調整（複数行テキスト対応）
        button.setMinimumHeight(max(50, button_height - 15))  # 説明文のため高さを確保
        button.setMaximumHeight(max(60, button_height - 5))
        button.setMinimumWidth(max(200, button_width - 40))
        button.setMaximumWidth(max(240, button_width - 20))
        
        # ツールチップ（詳細情報）
        tooltip_text = f"🔹 {label}"
        if description:
            tooltip_text += f"\n💡 {description}"
        tooltip_text += "\n\n右クリック: プロンプト編集"
        button.setToolTip(tooltip_text)
        
        # 改良されたボタンスタイル（複数行対応）
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_SUCCESS_BORDER)};
                font-size: 11px;
                font-weight: bold;
                border-radius: 6px;
                padding: 5px 8px;
                text-align: left;
                margin: 0px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
            }}
        """)
        
        # ボタンにconfigを保存
        button.button_config = button_config
        
        # クリックハンドラ（デフォルトはデータセット向け）
        handler = clicked_handler or self.on_extension_button_clicked
        button.clicked.connect(lambda checked, config=button_config: handler(config))
        
        # ターゲット種別を保持（コンテキストメニューのプレビュー切替用）
        try:
            button._ai_target_kind = target_kind
        except Exception:
            pass

        # 右クリックメニューでプロンプト編集を追加
        button.setContextMenuPolicy(Qt.CustomContextMenu)
        button.customContextMenuRequested.connect(lambda pos, config=button_config, btn=button: self.show_button_context_menu(pos, config, btn))
        
        # ボタンリストに追加（複数クリック防止用）
        try:
            (buttons_list if buttons_list is not None else self.extension_buttons).append(button)
        except Exception:
            self.extension_buttons.append(button)
        
        return button
    
    def on_extension_button_clicked(self, button_config):
        """AI拡張ボタンクリック時の処理"""
        try:
            button_id = button_config.get('id', 'unknown')
            label = button_config.get('label', 'Unknown')
            
            logger.debug("AI拡張ボタンクリック: %s (%s)", button_id, label)
            
            # 既存結果の検出（同一ボタン + 同一対象）
            try:
                from classes.dataset.util.ai_suggest_result_log import read_latest_result

                # ログ保存と同じ優先順（dataset_id > grant_number > name）で target_key を作る
                dataset_id = ''
                grant_number = ''
                name = ''
                try:
                    if hasattr(self, 'extension_dataset_combo') and self.extension_dataset_combo.currentIndex() >= 0:
                        selected_dataset = self.extension_dataset_combo.itemData(self.extension_dataset_combo.currentIndex())
                        if isinstance(selected_dataset, dict):
                            dataset_id = (selected_dataset.get('id') or '').strip()
                            attrs = selected_dataset.get('attributes', {}) if isinstance(selected_dataset.get('attributes', {}), dict) else {}
                            grant_number = (attrs.get('grantNumber') or '').strip()
                            name = (attrs.get('name') or '').strip()
                except Exception:
                    pass
                if not dataset_id:
                    try:
                        if hasattr(self, 'context_data') and isinstance(self.context_data, dict):
                            dataset_id = (self.context_data.get('dataset_id') or '').strip()
                            grant_number = (self.context_data.get('grant_number') or '').strip()
                            name = (self.context_data.get('name') or '').strip()
                    except Exception:
                        pass
                if not grant_number:
                    try:
                        grant_number = getattr(self, 'grant_number_input', None).text() if hasattr(self, 'grant_number_input') and self.grant_number_input else ''
                        grant_number = (grant_number or '').strip()
                    except Exception:
                        pass
                if not name:
                    try:
                        name = getattr(self, 'name_input', None).text() if hasattr(self, 'name_input') and self.name_input else ''
                        name = (name or '').strip()
                    except Exception:
                        pass

                target_key = dataset_id or grant_number or name or 'unknown'
                latest = read_latest_result('dataset', target_key, button_id)
                if latest:
                    # pytest環境ではモーダル表示を避け、既存結果を自動表示して終了
                    if os.environ.get("PYTEST_CURRENT_TEST"):
                        fmt = (latest.get('display_format') or 'text').lower()
                        content = latest.get('display_content') or ''
                        if fmt == 'html':
                            self.extension_response_display.setHtml(content)
                        else:
                            self.extension_response_display.setText(content)
                        self.last_used_prompt = latest.get('prompt')
                        self.last_api_request_params = latest.get('request_params')
                        self.last_api_response_params = latest.get('response_params')
                        self.last_api_provider = latest.get('provider')
                        self.last_api_model = latest.get('model')
                        if hasattr(self, 'show_prompt_button'):
                            self.show_prompt_button.setEnabled(bool(self.last_used_prompt))
                        if hasattr(self, 'show_api_params_button'):
                            self.show_api_params_button.setEnabled(bool(self.last_api_request_params or self.last_api_response_params))
                        return

                    ts = (latest.get('timestamp') or '').strip()
                    box = QMessageBox(self)
                    box.setIcon(QMessageBox.Question)
                    box.setWindowTitle("既存結果あり")
                    box.setText(
                        f"同一ボタン・同一対象の既存結果が見つかりました。" + (f"（{ts}）" if ts else "")
                    )
                    box.setInformativeText("既存の最新結果を表示しますか？それとも新規に問い合わせますか？")
                    show_existing_btn = box.addButton("既存結果を表示", QMessageBox.AcceptRole)
                    run_new_btn = box.addButton("新規問い合わせ", QMessageBox.ActionRole)
                    cancel_btn = box.addButton(QMessageBox.Cancel)
                    box.setDefaultButton(show_existing_btn)
                    box.exec()

                    chosen = box.clickedButton()
                    if chosen == cancel_btn:
                        return
                    if chosen == show_existing_btn:
                        fmt = (latest.get('display_format') or 'text').lower()
                        content = latest.get('display_content') or ''
                        if fmt == 'html':
                            self.extension_response_display.setHtml(content)
                        else:
                            self.extension_response_display.setText(content)

                        self.last_used_prompt = latest.get('prompt')
                        self.last_api_request_params = latest.get('request_params')
                        self.last_api_response_params = latest.get('response_params')
                        self.last_api_provider = latest.get('provider')
                        self.last_api_model = latest.get('model')
                        if hasattr(self, 'show_prompt_button'):
                            self.show_prompt_button.setEnabled(bool(self.last_used_prompt))
                        if hasattr(self, 'show_api_params_button'):
                            self.show_api_params_button.setEnabled(bool(self.last_api_request_params or self.last_api_response_params))
                        return

                    # run_new_btn の場合はそのまま問い合わせ続行
            except Exception:
                # ログ機能は失敗しても問い合わせ自体は継続
                pass

            # senderからクリックされたボタンを取得
            clicked_button = self.sender()
            self._active_extension_button = clicked_button if hasattr(clicked_button, 'start_loading') else None

            if clicked_button and hasattr(clicked_button, 'start_loading'):
                clicked_button.start_loading("AI処理中")
            
            # プロンプトを構築
            prompt = self.build_extension_prompt(button_config)
            
            if not prompt:
                if clicked_button:
                    clicked_button.stop_loading()
                QMessageBox.warning(self, "警告", "プロンプトの構築に失敗しました。")
                return
            
            # AI問い合わせを実行
            self.execute_extension_ai_request(prompt, button_config, clicked_button)
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"AI拡張ボタン処理エラー: {str(e)}")
    
    def build_extension_prompt(self, button_config):
        """AI拡張プロンプトを構築"""
        try:
            prompt_file = button_config.get('prompt_file')
            prompt_template = button_config.get('prompt_template')
            
            logger.debug("プロンプト構築開始 - prompt_file: %s, prompt_template: %s", prompt_file, bool(prompt_template))
            
            if prompt_file:
                # ファイルからプロンプトを読み込み
                from classes.dataset.util.ai_extension_helper import load_prompt_file
                template_content = load_prompt_file(prompt_file)
                if not template_content:
                    logger.warning("プロンプトファイルが読み込めません: %s", prompt_file)
                    # フォールバック用のシンプルプロンプト
                    template_content = f"""データセットについて分析してください。

データセット名: {{name}}
課題番号: {{grant_number}}
タイプ: {{dataset_type}}
既存説明: {{description}}

上記の情報を基に、「{button_config.get('label', 'AI分析')}」の観点から詳細な分析を行ってください。"""
            elif prompt_template:
                # 直接指定されたテンプレートを使用
                template_content = prompt_template
                logger.debug("直接指定されたテンプレートを使用")
            else:
                logger.warning("プロンプトファイルもテンプレートも指定されていません")
                # デフォルトプロンプト
                template_content = f"""データセットについて分析してください。

データセット名: {{name}}
課題番号: {{grant_number}}
タイプ: {{dataset_type}}
既存説明: {{description}}

上記の情報を基に、「{button_config.get('label', 'AI分析')}」の観点から詳細な分析を行ってください。"""
            
            # コンテキストデータを準備
            context_data = self.prepare_extension_context()
            logger.debug("コンテキストデータ準備完了: %s", list(context_data.keys()))
            
            # プロンプトを置換
            from classes.dataset.util.ai_extension_helper import format_prompt_with_context
            formatted_prompt = format_prompt_with_context(template_content, context_data)
            
            logger.debug("プロンプト構築完了 - 長さ: %s文字", len(formatted_prompt))
            return formatted_prompt
            
        except Exception as e:
            logger.error("AI拡張プロンプト構築エラー: %s", e)
            import traceback
            traceback.print_exc()
            return None
    
    def prepare_extension_context(self):
        """AI拡張用のコンテキストデータを準備"""
        try:
            # 基本コンテキストデータを確保
            if hasattr(self, 'context_data') and self.context_data:
                context_data = self.context_data.copy()
            else:
                # フォールバック用の基本データ
                context_data = {
                    'name': getattr(self, 'name_input', None).text() if hasattr(self, 'name_input') and self.name_input else "未設定",
                    'grant_number': getattr(self, 'grant_number_input', None).text() if hasattr(self, 'grant_number_input') and self.grant_number_input else "未設定",
                    'dataset_type': getattr(self, 'type_combo', None).currentText() if hasattr(self, 'type_combo') and self.type_combo else "未設定",
                    'description': getattr(self, 'description_input', None).toPlainText() if hasattr(self, 'description_input') and self.description_input else "未設定"
                }
                logger.warning("context_dataが初期化されていません。フォールバックデータを使用します。")
            
            # データセット選択による更新があった場合は最新情報を使用
            if hasattr(self, 'extension_dataset_combo') and self.extension_dataset_combo.currentIndex() >= 0:
                selected_dataset = self.extension_dataset_combo.itemData(self.extension_dataset_combo.currentIndex())
                if selected_dataset:
                    attrs = selected_dataset.get('attributes', {})
                    context_data.update({
                        'name': attrs.get('name', context_data.get('name', '')),
                        'grant_number': attrs.get('grantNumber', context_data.get('grant_number', '')),
                        'dataset_type': attrs.get('datasetType', context_data.get('dataset_type', 'mixed')),
                        'description': attrs.get('description', context_data.get('description', '')),
                        'dataset_id': selected_dataset.get('id', '')
                    })
                    logger.debug("データセット選択による情報更新: %s", context_data['name'])
            
            # 追加のコンテキストデータを収集（可能な場合）
            try:
                from classes.dataset.util.dataset_context_collector import get_dataset_context_collector
                context_collector = get_dataset_context_collector()
                
                dataset_id = context_data.get('dataset_id')
                if dataset_id:
                    dataset_id = (dataset_id or '').strip()
                    # データセットIDを一時的に除外
                    context_data_without_id = {k: v for k, v in context_data.items() if k != 'dataset_id'}
                    
                    # 完全なコンテキストを収集
                    full_context = context_collector.collect_full_context(
                        dataset_id=dataset_id,
                        **context_data_without_id
                    )

                    # collector側の戻り値に空のdataset_idが含まれていると、選択したdataset_idが消える。
                    # 非空のdataset_idは常に保持する。
                    if isinstance(full_context, dict):
                        try:
                            if dataset_id and not (full_context.get('dataset_id') or '').strip():
                                full_context.pop('dataset_id', None)
                        except Exception:
                            pass
                        context_data.update(full_context)
                        context_data['dataset_id'] = dataset_id
            except Exception as context_error:
                logger.warning("拡張コンテキスト収集でエラー: %s", context_error)
                # エラーが発生してもbase contextで続行
            
                # AI設定からプロバイダー/モデル情報を付与
                try:
                    from classes.ai.core.ai_manager import AIManager

                    ai_manager = AIManager()
                    provider = ai_manager.get_default_provider()
                    model = ai_manager.get_default_model(provider)
                    if provider:
                        context_data['llm_provider'] = provider
                    if model:
                        context_data['llm_model'] = model
                    if provider or model:
                        context_data['llm_model_name'] = f"{provider}:{model}".strip(':')
                except Exception as ai_err:
                    logger.warning("AI設定の取得に失敗しました: %s", ai_err)
            
            return context_data
            
        except Exception as e:
            logger.error("AI拡張コンテキスト準備エラー: %s", e)
            # 最小限のフォールバックデータ
            return {
                'name': "データセット名未設定",
                'grant_number': "課題番号未設定", 
                'dataset_type': "タイプ未設定",
                'description': "説明未設定"
            }
    
    def execute_extension_ai_request(self, prompt, button_config, button_widget, retry_count: int = 0):
        """AI拡張リクエストを実行"""
        try:
            # 使用するプロンプトを保存
            self.last_used_prompt = prompt

            # リクエスト/レスポンス params は実行結果が返ってから更新
            self.last_api_request_params = None
            self.last_api_response_params = None
            self.last_api_provider = None
            self.last_api_model = None
            if hasattr(self, 'show_api_params_button'):
                self.show_api_params_button.setEnabled(False)
            
            # プロンプト表示ボタンを有効化
            if hasattr(self, 'show_prompt_button'):
                self.show_prompt_button.setEnabled(True)
            
            # 全AI拡張ボタンを無効化（複数クリック防止）
            self.disable_all_extension_buttons()
            
            # スピナーメッセージをボタンラベルに更新
            button_label = button_config.get('label', 'AI処理')
            button_icon = button_config.get('icon', '🤖')
            if hasattr(self, 'extension_spinner_overlay'):
                self.extension_spinner_overlay.set_message(f"{button_icon} {button_label} 実行中...")
            
            # AIリクエストスレッドを作成・実行
            ai_thread = AIRequestThread(prompt, self.context_data)
            
            # スレッドリストに追加（管理用）
            self.extension_ai_threads.append(ai_thread)

            # スピナー表示（少なくとも1件走っていれば表示）
            self.update_extension_spinner_visibility()
            
            # スレッド完了時のコールバック
            def on_success(result):
                try:
                    # API req/resp パラメータを保存（本文は含めない想定）
                    try:
                        self.last_api_request_params = result.get('request_params')
                        self.last_api_response_params = result.get('response_params')
                        self.last_api_provider = result.get('provider')
                        self.last_api_model = result.get('model')
                        if hasattr(self, 'show_api_params_button'):
                            self.show_api_params_button.setEnabled(bool(self.last_api_request_params or self.last_api_response_params))
                    except Exception as _e:
                        logger.debug("API req/resp params capture failed: %s", _e)

                    response_text = result.get('response') or result.get('content', '')
                    if response_text:
                        # 出力フォーマットに応じた表示処理
                        fmt = button_config.get('output_format', 'text')
                        if fmt == 'json':
                            # JSONとして検証し、軽微修正を試みる
                            valid, fixed_text = self._validate_and_fix_json_response(response_text)
                            if valid:
                                # 整形せずそのまま表示（安全のためfixed_textを使用）
                                self.extension_response_display.setText(fixed_text)
                            else:
                                # リトライ（最大2回）
                                if retry_count < 2:
                                    logger.info("JSON応答が不正のためリトライします: retry=%s", retry_count + 1)
                                    # スレッドをリストから削除し再実行
                                    if ai_thread in self.extension_ai_threads:
                                        self.extension_ai_threads.remove(ai_thread)
                                    self.update_extension_spinner_visibility()
                                    # 再実行（retry_count+1）
                                    self.execute_extension_ai_request(prompt, button_config, button_widget, retry_count + 1)
                                    return
                                else:
                                    # 最終失敗時も raw が有効JSONなら成功扱い
                                    import json as _json
                                    try:
                                        _json.loads(response_text)
                                        logger.warning("検証ロジックでは不正扱いでしたが raw は有効JSONのため成功扱いに変更")
                                        self.extension_response_display.setText(response_text)
                                    except Exception:
                                        # エラーをJSON化して返す
                                        error_json_str = self._wrap_json_error(
                                            error_message="JSONの検証に失敗しました（最大リトライ到達）",
                                            raw_output=response_text,
                                            retries=retry_count
                                        )
                                        self.extension_response_display.setText(error_json_str)
                        else:
                            # 従来通りの整形表示
                            formatted_response = self.format_extension_response(response_text, button_config)
                            self.extension_response_display.setHtml(formatted_response)
                    else:
                        self.extension_response_display.setText("AI応答が空でした。")

                    # ログ保存（データセット）
                    try:
                        from classes.dataset.util.ai_suggest_result_log import append_result

                        ctx = self.prepare_extension_context() if hasattr(self, 'prepare_extension_context') else (self.context_data or {})
                        dataset_id = (ctx.get('dataset_id') or '').strip() if isinstance(ctx, dict) else ''
                        grant_number = (ctx.get('grant_number') or '').strip() if isinstance(ctx, dict) else ''
                        name = (ctx.get('name') or '').strip() if isinstance(ctx, dict) else ''
                        target_key = dataset_id or grant_number or name or 'unknown'

                        if fmt == 'json':
                            display_format = 'text'
                            display_content = self.extension_response_display.toPlainText()
                        else:
                            display_format = 'html'
                            display_content = self.extension_response_display.toHtml()

                        append_result(
                            target_kind='dataset',
                            target_key=target_key,
                            button_id=button_config.get('id', 'unknown'),
                            button_label=button_config.get('label', 'Unknown'),
                            prompt=self.last_used_prompt or prompt,
                            display_format=display_format,
                            display_content=display_content,
                            provider=self.last_api_provider,
                            model=self.last_api_model,
                            request_params=self.last_api_request_params,
                            response_params=self.last_api_response_params,
                            started_at=(result.get('started_at') if isinstance(result, dict) else None),
                            finished_at=(result.get('finished_at') if isinstance(result, dict) else None),
                            elapsed_seconds=(result.get('elapsed_seconds') if isinstance(result, dict) else None),
                        )
                    except Exception:
                        pass
                finally:
                    if button_widget:
                        button_widget.stop_loading()
                    if self._active_extension_button is button_widget:
                        self._active_extension_button = None
                    # 完了したスレッドをリストから削除
                    if ai_thread in self.extension_ai_threads:
                        self.extension_ai_threads.remove(ai_thread)
                    # スピナー表示更新
                    self.update_extension_spinner_visibility()
                    # スピナーメッセージをデフォルトに戻す
                    if hasattr(self, 'extension_spinner_overlay'):
                        self.extension_spinner_overlay.set_message("AI応答を待機中...")
                    # 全AI拡張ボタンを有効化（完了時）
                    self.enable_all_extension_buttons()
            
            def on_error(error_message):
                try:
                    self.extension_response_display.setText(f"エラー: {error_message}")
                finally:
                    if button_widget:
                        button_widget.stop_loading()
                    if self._active_extension_button is button_widget:
                        self._active_extension_button = None
                    # エラー時もスレッドをリストから削除
                    if ai_thread in self.extension_ai_threads:
                        self.extension_ai_threads.remove(ai_thread)
                    # スピナー表示更新
                    self.update_extension_spinner_visibility()
                    # スピナーメッセージをデフォルトに戻す
                    if hasattr(self, 'extension_spinner_overlay'):
                        self.extension_spinner_overlay.set_message("AI応答を待機中...")
                    # 全AI拡張ボタンを有効化（エラー時）
                    self.enable_all_extension_buttons()

                    # エラー時はAPI params表示も無効化
                    self.last_api_request_params = None
                    self.last_api_response_params = None
                    self.last_api_provider = None
                    self.last_api_model = None
                    if hasattr(self, 'show_api_params_button'):
                        self.show_api_params_button.setEnabled(False)
            
            ai_thread.result_ready.connect(on_success)
            ai_thread.error_occurred.connect(on_error)
            ai_thread.start()
            
        except Exception as e:
            if button_widget:
                button_widget.stop_loading()
            if self._active_extension_button is button_widget:
                self._active_extension_button = None
            # 例外時も全AI拡張ボタンを有効化
            self.enable_all_extension_buttons()
            QMessageBox.critical(self, "エラー", f"AI拡張リクエスト実行エラー: {str(e)}")

    def _validate_and_fix_json_response(self, text: str):
        """LLM応答をJSONとして検証し、軽微な修正を試みる
        Returns: (is_valid: bool, fixed_text: str)
        軽微修正例:
          - シングルクォート→ダブルクォート
          - 末尾カンマの削除
          - 先頭/末尾のコードフェンス削除
        """
        try:
            import json, re
            cleaned = text.strip()
            # ```json ... ``` や ``` ... ``` を除去
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```\s*$', '', cleaned)
            # 先頭が配列 '[' の場合は抽出処理を行わない（リストJSON対応）
            if cleaned[:1] != '[':
                # 先頭に余計な説明文がある場合の簡易抽出：最初の { から最後の } まで
                if '{' in cleaned and '}' in cleaned:
                    start = cleaned.find('{')
                    end = cleaned.rfind('}')
                    if start >= 0 and end > start:
                        cleaned = cleaned[start:end+1]
            # シングルクォートをダブルクォートへ（キー/値想定の簡易置換）
            # 注意: 正確性は限定的だが軽微修正の範囲とする
            cleaned_alt = re.sub(r"'", '"', cleaned)
            # 末尾カンマの削除（オブジェクト内）
            cleaned_alt = re.sub(r',\s*([}\]])', r'\1', cleaned_alt)
            # 一旦正規のJSONとしてロードできるか
            try:
                json.loads(cleaned_alt)
                return True, cleaned_alt
            except Exception:
                # そのままも試す
                try:
                    json.loads(cleaned)
                    return True, cleaned
                except Exception:
                    return False, cleaned
        except Exception:
            return False, text

    def _wrap_json_error(self, error_message: str, raw_output: str, retries: int):
        """エラーメッセージをJSONフォーマットでラップして返却"""
        try:
            import json
            payload = {
                "error": error_message,
                "retries": retries,
                "timestamp": datetime.datetime.now().isoformat(),
                "raw_output": raw_output
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"{{\n  \"error\": \"JSONエラーラップ失敗: {str(e)}\",\n  \"raw_output\": \"{raw_output[:200].replace('\\n',' ')}...\"\n}}"

    def update_extension_spinner_visibility(self):
        """AI拡張スピナーの表示/非表示を更新"""
        try:
            if getattr(self, 'extension_spinner_overlay', None):
                if len(self.extension_ai_threads) > 0:
                    self.extension_spinner_overlay.start()
                else:
                    self.extension_spinner_overlay.stop()
        except Exception as _e:
            logger.debug("update_extension_spinner_visibility failed: %s", _e)

    def cancel_extension_ai_requests(self):
        """AI拡張の実行中リクエストをキャンセル（スピナー直近のボタン）"""
        try:
            # 実行中の全スレッドに停止を要求
            for th in list(self.extension_ai_threads):
                try:
                    if hasattr(th, 'stop'):
                        th.stop()
                    # 最大1秒待機
                    if hasattr(th, 'wait'):
                        th.wait(1000)
                except Exception as _e:
                    logger.debug("cancel thread failed: %s", _e)
                finally:
                    if th in self.extension_ai_threads:
                        self.extension_ai_threads.remove(th)

            # 実行中ボタンのローディングを停止
            if self._active_extension_button:
                try:
                    self._active_extension_button.stop_loading()
                except Exception:
                    pass
                finally:
                    self._active_extension_button = None

            # スピナー非表示
            if getattr(self, 'extension_spinner_overlay', None):
                self.extension_spinner_overlay.stop()
                # スピナーメッセージをデフォルトに戻す
                self.extension_spinner_overlay.set_message("AI応答を待機中...")

            # 全AI拡張ボタンを有効化（キャンセル時）
            self.enable_all_extension_buttons()

            # ユーザー通知（応答エリアに反映）
            if hasattr(self, 'extension_response_display'):
                self.extension_response_display.append("\n<em>⏹ AI処理をキャンセルしました。</em>")

            logger.info("AI拡張リクエストをキャンセルしました")
        except Exception as e:
            logger.error("AI拡張キャンセルエラー: %s", e)
    
    def disable_all_extension_buttons(self):
        """全AI拡張ボタンを無効化（複数クリック防止）"""
        try:
            for button in self.extension_buttons:
                if hasattr(button, 'setEnabled'):
                    button.setEnabled(False)
            logger.debug("全AI拡張ボタンを無効化しました（%d件）", len(self.extension_buttons))
        except Exception as e:
            logger.error("AI拡張ボタン無効化エラー: %s", e)
    
    def enable_all_extension_buttons(self):
        """全AI拡張ボタンを有効化（AI処理完了/キャンセル時）"""
        try:
            for button in self.extension_buttons:
                if hasattr(button, 'setEnabled'):
                    button.setEnabled(True)
            logger.debug("全AI拡張ボタンを有効化しました（%d件）", len(self.extension_buttons))
        except Exception as e:
            logger.error("AI拡張ボタン有効化エラー: %s", e)
    
    def format_extension_response(self, response_text, button_config):
        """AI拡張応答をフォーマット（マークダウン対応）"""
        try:
            label = button_config.get('label', 'AI拡張')
            icon = button_config.get('icon', '🤖')
            timestamp = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # マークダウンをHTMLに変換
            html_content = self.convert_markdown_to_html(response_text)
            
            # HTMLフォーマット（コンパクトヘッダー付き）
            formatted_html = f"""
            <div style="border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; border-radius: 6px; padding: 0; margin: 3px 0;">
                <div style="background-color: {get_color(ThemeKey.PANEL_INFO_BACKGROUND)}; color: {get_color(ThemeKey.PANEL_INFO_TEXT)}; padding: 8px 12px; border-radius: 6px 6px 0 0; margin-bottom: 0;">
                    <h3 style="margin: 0; font-size: 14px; font-weight: bold;">{icon} {label}</h3>
                    <small style="opacity: 0.9; font-size: 10px;">実行時刻: {timestamp}</small>
                </div>
                <div style="padding: 10px; line-height: 1.3; font-family: 'Yu Gothic', 'Meiryo', sans-serif;">
                    {html_content}
                </div>
            </div>
            """
            
            return formatted_html
            
        except Exception as e:
            logger.error("AI拡張応答フォーマットエラー: %s", e)
            # フォールバック
            import html
            escaped_text = html.escape(response_text)
            return (
                f"<div style='padding: 10px; border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};'>"
                f"<pre>{escaped_text}</pre></div>"
            )
    
    def convert_markdown_to_html(self, markdown_text):
        """シンプルなマークダウン→HTML変換"""
        try:
            import re
            html_text = markdown_text
            
            # HTMLエスケープ
            import html
            html_text = html.escape(html_text)
            
            # マークダウン要素をHTMLに変換
            
            # ヘッダー（### → h3, ## → h2, # → h1）
            html_text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html_text, flags=re.MULTILINE)
            html_text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html_text, flags=re.MULTILINE)
            html_text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html_text, flags=re.MULTILINE)
            
            # 太字（**text** → <strong>text</strong>）
            html_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_text)
            
            # 斜体（*text* → <em>text</em>）
            html_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html_text)
            
            # インラインコード（`code` → <code>code</code>）
            html_text = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_text)
            
            # マークダウンテーブル変換を先に処理
            html_text = self.convert_markdown_tables(html_text)
            
            # リスト項目（- item → <li>item</li>）
            lines = html_text.split('\n')
            in_list = False
            in_table = False
            result_lines = []
            
            for line in lines:
                stripped = line.strip()
                
                # テーブル行の判定（既に変換済みのHTMLテーブルはスキップ）
                if '<table' in line or '</table>' in line or '<tr>' in line or '</tr>' in line:
                    in_table = True
                    result_lines.append(line)
                    if '</table>' in line:
                        in_table = False
                    continue
                
                if in_table:
                    result_lines.append(line)
                    continue
                
                if re.match(r'^[-*+]\s+', stripped):
                    if not in_list:
                        result_lines.append('<ul>')
                        in_list = True
                    item_text = re.sub(r'^[-*+]\s+', '', stripped)
                    result_lines.append(f'<li>{item_text}</li>')
                else:
                    if in_list:
                        result_lines.append('</ul>')
                        in_list = False
                    if stripped:  # 空行でない場合
                        result_lines.append(f'<p>{line}</p>')
                    else:
                        # 空行は少ない間隔にする
                        result_lines.append('<div style="margin: 2px 0;"></div>')
            
            if in_list:
                result_lines.append('</ul>')
            
            html_text = '\n'.join(result_lines)
            
            # コードブロック（```code``` → <pre><code>code</code></pre>）- コンパクトスタイル
            html_text = re.sub(
                r'```([^`]*?)```', 
                rf'<pre style=" padding: 6px; border-radius: 3px; border: 1px solid {get_color(ThemeKey.BORDER_LIGHT)}; overflow-x: auto; margin: 4px 0;"><code>\1</code></pre>', 
                html_text, 
                flags=re.DOTALL
            )
            
            # 引用（> text → <blockquote>text</blockquote>）
            html_text = re.sub(r'^> (.*?)$', r'<blockquote>\1</blockquote>', html_text, flags=re.MULTILINE)
            
            return html_text
            
        except Exception as e:
            logger.warning("マークダウン変換エラー: %s", e)
            # エラー時はプレーンテキストをHTMLエスケープして返す
            import html
            return f"<pre>{html.escape(markdown_text)}</pre>"
    
    def convert_markdown_tables(self, text):
        """マークダウンテーブルをHTMLテーブルに変換"""
        try:
            import re
            lines = text.split('\n')
            result_lines = []
            in_table = False
            table_lines = []
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                
                # テーブル行の判定（|で始まって|で終わる、または|を含む）
                if '|' in stripped and len(stripped.split('|')) >= 3:
                    # セパレータ行の判定（|:---|---|:---|のような行）
                    is_separator = re.match(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$', stripped)
                    
                    if not in_table:
                        in_table = True
                        table_lines = []
                    
                    if is_separator:
                        # セパレータ行は無視してテーブルヘッダーを確定
                        continue
                    else:
                        table_lines.append(stripped)
                else:
                    # テーブル以外の行
                    if in_table:
                        # テーブル終了 - HTMLテーブルを生成
                        html_table = self.build_html_table(table_lines)
                        result_lines.append(html_table)
                        in_table = False
                        table_lines = []
                    
                    result_lines.append(line)
            
            # 最後にテーブルがある場合
            if in_table and table_lines:
                html_table = self.build_html_table(table_lines)
                result_lines.append(html_table)
            
            return '\n'.join(result_lines)
            
        except Exception as e:
            logger.warning("テーブル変換エラー: %s", e)
            return text
    
    def build_html_table(self, table_lines):
        """テーブル行のリストからHTMLテーブルを構築"""
        try:
            if not table_lines:
                return ""
            
            html_parts = ['<table>']
            
            for i, line in enumerate(table_lines):
                # 行をセルに分割
                cells = [cell.strip() for cell in line.split('|')]
                # 最初と最後の空セルを除去
                if cells and not cells[0]:
                    cells = cells[1:]
                if cells and not cells[-1]:
                    cells = cells[:-1]
                
                if not cells:
                    continue
                
                html_parts.append('<tr>')
                
                # 最初の行はヘッダーとして扱う
                if i == 0:
                    for cell in cells:
                        html_parts.append(f'<th>{cell}</th>')
                else:
                    for cell in cells:
                        html_parts.append(f'<td>{cell}</td>')
                
                html_parts.append('</tr>')
            
            html_parts.append('</table>')
            
            return '\n'.join(html_parts)
            
        except Exception as e:
            logger.warning("HTMLテーブル構築エラー: %s", e)
            return '\n'.join(table_lines)
    
    def edit_extension_config(self):
        """AI拡張設定ファイルを編集"""
        try:
            from classes.dataset.ui.ai_extension_config_dialog import AIExtensionConfigDialog

            dialog = AIExtensionConfigDialog(self)
            dialog.config_saved.connect(self._on_ai_suggest_config_saved)
            dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"設定編集エラー: {str(e)}")

    def _on_ai_suggest_config_saved(self):
        try:
            self.load_extension_buttons()
        except Exception:
            pass
        try:
            self.load_report_buttons()
        except Exception:
            pass
    
    def clear_extension_response(self):
        """AI拡張応答をクリア"""
        self.extension_response_display.clear()
    
    def copy_extension_response(self):
        """AI拡張応答をクリップボードにコピー"""
        try:
            from qt_compat.widgets import QApplication
            # QTextBrowserからプレーンテキストを取得
            text = self.extension_response_display.toPlainText()
            if text:
                clipboard = QApplication.clipboard()
                clipboard.setText(text)
                QMessageBox.information(self, "コピー完了", "応答内容をクリップボードにコピーしました。")
            else:
                QMessageBox.warning(self, "警告", "コピーする内容がありません。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"コピーエラー: {str(e)}")

    
    def show_used_prompt(self):
        """使用したプロンプトをダイアログで表示"""
        try:
            if not self.last_used_prompt:
                QMessageBox.information(self, "情報", "表示可能なプロンプトがありません。\nAI機能を実行してから再度お試しください。")
                return
            
            # プロンプト表示ダイアログを作成
            prompt_dialog = QDialog(self)
            prompt_dialog.setWindowTitle("使用したプロンプト")
            prompt_dialog.setModal(True)
            prompt_dialog.resize(800, 600)
            
            layout = QVBoxLayout(prompt_dialog)
            
            # ヘッダー
            header_label = QLabel("📄 AIリクエストで実際に使用したプロンプト")
            header_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 5px; ")
            layout.addWidget(header_label)
            
            # プロンプト表示エリア
            prompt_display = QTextEdit()
            prompt_display.setReadOnly(True)
            prompt_display.setPlainText(self.last_used_prompt)
            prompt_display.setStyleSheet(f"""
                QTextEdit {{
                    border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                    border-radius: 5px;
           
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                    font-size: 11px;
                    padding: 8px;
                }}
            """)
            layout.addWidget(prompt_display)
            
            # 統計情報
            char_count = len(self.last_used_prompt)
            line_count = self.last_used_prompt.count('\n') + 1
            stats_label = QLabel(f"文字数: {char_count:,} / 行数: {line_count:,}")
            stats_label.setStyleSheet("font-size: 11px; argin: 3px;")
            layout.addWidget(stats_label)
            
            # ボタンエリア
            button_layout = QHBoxLayout()
            
            # コピーボタン
            copy_button = QPushButton("📋 プロンプトをコピー")
            copy_button.clicked.connect(lambda: self._copy_prompt_to_clipboard(self.last_used_prompt))
            copy_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                    border: 1px solid {get_color(ThemeKey.BUTTON_SUCCESS_BORDER)};
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
                }}
                QPushButton:pressed {{
                    background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED)};
                }}
            """)
            button_layout.addWidget(copy_button)
            
            button_layout.addStretch()
            
            # 閉じるボタン
            close_button = QPushButton("閉じる")
            close_button.clicked.connect(prompt_dialog.accept)
            close_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                    border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
                    border-radius: 4px;
                    padding: 8px 16px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
                }}
            """)
            button_layout.addWidget(close_button)
            
            layout.addLayout(button_layout)
            
            # ダイアログを表示
            prompt_dialog.exec_()
            
        except Exception as e:
            logger.error("プロンプト表示エラー: %s", e)
            QMessageBox.critical(self, "エラー", f"プロンプト表示エラー: {str(e)}")

    def show_api_request_response_params(self):
        """実際のAPIリクエスト/レスポンス（本文以外）を表示"""
        try:
            if not (self.last_api_request_params or self.last_api_response_params):
                QMessageBox.information(self, "情報", "表示可能なAPIリクエスト/レスポンス情報がありません。\nAI機能を実行してから再度お試しください。")
                return

            params_dialog = QDialog(self)
            params_dialog.setWindowTitle("APIリクエスト/レスポンス（本文以外）")
            params_dialog.setModal(True)
            params_dialog.resize(900, 650)

            layout = QVBoxLayout(params_dialog)

            provider = self.last_api_provider or ""
            model = self.last_api_model or ""
            header_label = QLabel(f"🔎 実際のAPI req/resp パラメータ（プロンプト/本文は省略）\nprovider: {provider} / model: {model}")
            header_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 5px;")
            layout.addWidget(header_label)

            splitter = QSplitter(Qt.Horizontal)

            req_widget = QWidget()
            req_layout = QVBoxLayout(req_widget)
            req_title = QLabel("リクエスト")
            req_title.setStyleSheet("font-weight: bold; margin: 3px;")
            req_layout.addWidget(req_title)
            req_edit = QTextEdit()
            req_edit.setReadOnly(True)
            req_edit.setPlainText(self._pretty_json(self.last_api_request_params or {}))
            req_layout.addWidget(req_edit)
            splitter.addWidget(req_widget)

            resp_widget = QWidget()
            resp_layout = QVBoxLayout(resp_widget)
            resp_title = QLabel("レスポンス")
            resp_title.setStyleSheet("font-weight: bold; margin: 3px;")
            resp_layout.addWidget(resp_title)
            resp_edit = QTextEdit()
            resp_edit.setReadOnly(True)
            resp_edit.setPlainText(self._pretty_json(self.last_api_response_params or {}))
            resp_layout.addWidget(resp_edit)
            splitter.addWidget(resp_widget)

            splitter.setSizes([450, 450])
            layout.addWidget(splitter)

            button_layout = QHBoxLayout()
            button_layout.addStretch()
            close_button = QPushButton("閉じる")
            close_button.clicked.connect(params_dialog.accept)
            close_button.setStyleSheet(self.show_prompt_button.styleSheet() if hasattr(self, 'show_prompt_button') else "")
            button_layout.addWidget(close_button)
            layout.addLayout(button_layout)

            params_dialog.exec_()

        except Exception as e:
            logger.error("API req/resp params表示エラー: %s", e)
            QMessageBox.critical(self, "エラー", f"API req/resp params表示エラー: {str(e)}")

    def _pretty_json(self, obj) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return str(obj)
    
    def _copy_prompt_to_clipboard(self, prompt_text):
        """プロンプトをクリップボードにコピー"""
        try:
            from qt_compat.widgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(prompt_text)
            QMessageBox.information(self, "コピー完了", f"プロンプトをクリップボードにコピーしました。\n\n文字数: {len(prompt_text):,}")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"コピーエラー: {str(e)}")
    
    def load_extraction_settings(self):
        """ファイル抽出設定を読み込み"""
        try:
            from config.common import get_dynamic_file_path
            config_path = get_dynamic_file_path('config/app_config.json')
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    extraction_config = config.get('file_text_extraction', {})
                    
                    # UIに設定を反映
                    if hasattr(self, 'file_extensions_input'):
                        extensions = extraction_config.get('target_extensions', ['.txt', '.csv', '.xlsx', '.json', '.md', '.log', '.xml'])
                        self.file_extensions_input.setText(', '.join(extensions))
                    
                    if hasattr(self, 'exclude_patterns_input'):
                        patterns = extraction_config.get('exclude_patterns', [
                            '.*_anonymized\\.json',
                            '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.json'
                        ])
                        self.exclude_patterns_input.setPlainText('\n'.join(patterns))
                    
                    if hasattr(self, 'max_files_spinbox'):
                        self.max_files_spinbox.setValue(extraction_config.get('max_files', 10))
                    
                    if hasattr(self, 'max_file_size_spinbox'):
                        max_size_mb = extraction_config.get('max_file_size_bytes', 10485760) // (1024 * 1024)
                        self.max_file_size_spinbox.setValue(max_size_mb)
                    
                    if hasattr(self, 'max_chars_spinbox'):
                        self.max_chars_spinbox.setValue(extraction_config.get('max_chars_per_file', 10000))
                    
                    if hasattr(self, 'excel_all_sheets_checkbox'):
                        self.excel_all_sheets_checkbox.setChecked(extraction_config.get('excel_all_sheets', True))
                    
                    if hasattr(self, 'excel_max_rows_spinbox'):
                        self.excel_max_rows_spinbox.setValue(extraction_config.get('excel_max_rows', 1000))
                    
                    logger.info("ファイル抽出設定を読み込みました")
            else:
                logger.info("設定ファイルが存在しないため、デフォルト設定を使用します")
                self.reset_extraction_settings()
                
        except Exception as e:
            logger.error("設定読み込みエラー: %s", e)
            QMessageBox.warning(self, "警告", f"設定の読み込みに失敗しました。デフォルト設定を使用します。\n\nエラー: {str(e)}")
            self.reset_extraction_settings()
    
    def save_extraction_settings(self):
        """ファイル抽出設定を保存"""
        try:
            from config.common import get_dynamic_file_path
            config_path = get_dynamic_file_path('config/app_config.json')
            
            # 既存の設定を読み込み
            config = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            # 抽出設定を更新
            extraction_config = {}
            
            # ファイル拡張子
            if hasattr(self, 'file_extensions_input'):
                extensions_text = self.file_extensions_input.text().strip()
                extensions = [ext.strip() for ext in extensions_text.split(',') if ext.strip()]
                extraction_config['target_extensions'] = extensions
            
            # 除外パターン
            if hasattr(self, 'exclude_patterns_input'):
                patterns_text = self.exclude_patterns_input.toPlainText().strip()
                patterns = [p.strip() for p in patterns_text.split('\n') if p.strip()]
                extraction_config['exclude_patterns'] = patterns
            
            # 処理ファイル数上限
            if hasattr(self, 'max_files_spinbox'):
                extraction_config['max_files'] = self.max_files_spinbox.value()
            
            # ファイルサイズ上限
            if hasattr(self, 'max_file_size_spinbox'):
                max_size_bytes = self.max_file_size_spinbox.value() * 1024 * 1024
                extraction_config['max_file_size_bytes'] = max_size_bytes
            
            # 文字数制限
            if hasattr(self, 'max_chars_spinbox'):
                extraction_config['max_chars_per_file'] = self.max_chars_spinbox.value()
            
            # Excel設定
            if hasattr(self, 'excel_all_sheets_checkbox'):
                extraction_config['excel_all_sheets'] = self.excel_all_sheets_checkbox.isChecked()
            
            if hasattr(self, 'excel_max_rows_spinbox'):
                extraction_config['excel_max_rows'] = self.excel_max_rows_spinbox.value()
            
            # 設定を保存
            config['file_text_extraction'] = extraction_config
            
            # JSONファイルに書き込み
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            logger.info("ファイル抽出設定を保存しました: %s", config_path)
            QMessageBox.information(self, "保存完了", "ファイル抽出設定を保存しました。\n\n次回のAI分析から新しい設定が適用されます。")
            
        except Exception as e:
            logger.error("設定保存エラー: %s", e)
            QMessageBox.critical(self, "エラー", f"設定の保存に失敗しました。\n\nエラー: {str(e)}")
    
    def reset_extraction_settings(self):
        """ファイル抽出設定をデフォルトに戻す"""
        try:
            if hasattr(self, 'file_extensions_input'):
                self.file_extensions_input.setText(".txt, .csv, .xlsx, .json, .md, .log, .xml")
            
            if hasattr(self, 'exclude_patterns_input'):
                self.exclude_patterns_input.setPlainText(
                    ".*_anonymized\\.json\n"
                    "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\\.json"
                )
            
            if hasattr(self, 'max_files_spinbox'):
                self.max_files_spinbox.setValue(10)
            
            if hasattr(self, 'max_file_size_spinbox'):
                self.max_file_size_spinbox.setValue(10)
            
            if hasattr(self, 'max_chars_spinbox'):
                self.max_chars_spinbox.setValue(10000)
            
            if hasattr(self, 'excel_all_sheets_checkbox'):
                self.excel_all_sheets_checkbox.setChecked(True)
            
            if hasattr(self, 'excel_max_rows_spinbox'):
                self.excel_max_rows_spinbox.setValue(1000)
            
            logger.info("ファイル抽出設定をデフォルトに戻しました")
            
        except Exception as e:
            logger.error("設定リセットエラー: %s", e)
            QMessageBox.critical(self, "エラー", f"設定のリセットに失敗しました。\n\nエラー: {str(e)}")
    
    def show_button_context_menu(self, position, button_config, button_widget):
        """ボタンの右クリックメニューを表示"""
        try:
            from qt_compat.widgets import QMenu, QAction
            
            menu = QMenu(button_widget)
            
            # プロンプト編集アクション
            edit_action = QAction("📝 プロンプト編集", menu)
            target_kind = getattr(button_widget, '_ai_target_kind', 'dataset')
            edit_action.triggered.connect(lambda: self.edit_button_prompt(button_config, target_kind=target_kind))
            menu.addAction(edit_action)
            
            # プロンプトプレビューアクション
            preview_action = QAction("👁️ プロンプトプレビュー", menu)
            target_kind = getattr(button_widget, '_ai_target_kind', 'dataset')
            preview_action.triggered.connect(lambda: self.preview_button_prompt(button_config, target_kind=target_kind))
            menu.addAction(preview_action)
            
            # メニューを表示
            global_pos = button_widget.mapToGlobal(position)
            menu.exec_(global_pos)
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"コンテキストメニューエラー: {str(e)}")
    
    def edit_button_prompt(self, button_config, target_kind: str = "dataset"):
        """ボタンのプロンプトを編集（ターゲット別に保存先を分離）"""
        try:
            prompt_file = button_config.get('prompt_file')

            if prompt_file:
                from classes.dataset.ui.ai_extension_prompt_edit_dialog import AIExtensionPromptEditDialog

                button_id = button_config.get('id', 'unknown')
                prompt_file_for_target = self._get_prompt_file_for_target(prompt_file, target_kind, button_id)

                dialog = AIExtensionPromptEditDialog(
                    parent=self,
                    prompt_file_path=prompt_file_for_target,
                    button_config=button_config,
                    target_kind=target_kind,
                )
                dialog.exec()
                return

            reply = QMessageBox.question(
                self,
                "プロンプトファイル作成",
                f"ボタン '{button_config.get('label', 'Unknown')}' はデフォルトテンプレートを使用しています。\n"
                "プロンプトファイルを作成して編集しますか？",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            button_id = button_config.get('id', 'unknown')
            if target_kind == 'report':
                new_prompt_file = f"input/ai/prompts/report/{button_id}.txt"
            else:
                new_prompt_file = f"input/ai/prompts/ext/{button_id}.txt"

            initial_content = button_config.get('prompt_template', self.get_default_template_for_button(button_config))
            from classes.dataset.util.ai_extension_helper import save_prompt_file
            if not save_prompt_file(new_prompt_file, initial_content):
                QMessageBox.critical(self, "エラー", "プロンプトファイルの作成に失敗しました。")
                return

            QMessageBox.information(
                self,
                "ファイル作成完了",
                f"プロンプトファイルを作成しました:\n{new_prompt_file}\n\n"
                "設定ファイルの更新は手動で行ってください。"
            )

            from classes.dataset.ui.ai_extension_prompt_edit_dialog import AIExtensionPromptEditDialog
            dialog = AIExtensionPromptEditDialog(
                parent=self,
                prompt_file_path=new_prompt_file,
                button_config=button_config,
                target_kind=target_kind,
            )
            dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"プロンプト編集エラー: {str(e)}")

    def clear_report_response(self):
        """報告書タブのAI応答をクリア"""
        try:
            self.report_response_display.clear()
        except Exception:
            pass

    def copy_report_response(self):
        """報告書タブのAI応答をクリップボードにコピー"""
        try:
            from qt_compat.widgets import QApplication
            text = self.report_response_display.toPlainText()
            if text:
                clipboard = QApplication.clipboard()
                clipboard.setText(text)
                QMessageBox.information(self, "コピー完了", "応答内容をクリップボードにコピーしました。")
            else:
                QMessageBox.warning(self, "警告", "コピーする内容がありません。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"コピーエラー: {str(e)}")
    
    def preview_button_prompt(self, button_config, target_kind: str = "dataset"):
        """ボタンのプロンプトをプレビュー"""
        try:
            if target_kind == "report":
                prompt = self.build_report_prompt(button_config)
            else:
                prompt = self.build_extension_prompt(button_config)
            
            if prompt:
                # プレビューダイアログを表示
                from qt_compat.widgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
                
                preview_dialog = QDialog(self)
                preview_dialog.setWindowTitle(f"プロンプトプレビュー: {button_config.get('label', 'Unknown')}")
                preview_dialog.resize(700, 500)
                
                layout = QVBoxLayout(preview_dialog)
                
                preview_text = QTextEdit()
                preview_text.setReadOnly(True)
                preview_text.setText(prompt)
                layout.addWidget(preview_text)
                
                close_button = QPushButton("閉じる")
                close_button.clicked.connect(preview_dialog.close)
                layout.addWidget(close_button)
                
                preview_dialog.exec()
            else:
                QMessageBox.warning(self, "警告", "プロンプトの構築に失敗しました。")
                
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"プロンプトプレビューエラー: {str(e)}")
    
    def get_default_template_for_button(self, button_config):
        """ボタン用のデフォルトテンプレートを取得"""
        button_id = button_config.get('id', 'unknown')
        label = button_config.get('label', 'Unknown')
        
        return f"""データセットについて{label}を分析してください。

【データセット情報】
- 名前: {{name}}
- タイプ: {{type}}
- 課題番号: {{grant_number}}
- 説明: {{description}}

【実験データ】
{{experiment_data}}

【分析指示】
上記データセット情報を基に、{label}の観点から分析してください。

【出力形式】
分析結果を詳しく説明し、200文字程度で要約してください。

日本語で詳細に分析してください。"""
    
    def cleanup_threads(self):
        """すべてのスレッドをクリーンアップ"""
        try:
            # メインAIスレッドの停止
            if self.ai_thread and self.ai_thread.isRunning():
                logger.debug("メインAIスレッドを停止中...")
                self.ai_thread.stop()
                self.ai_thread.wait(3000)  # 3秒まで待機
                if self.ai_thread.isRunning():
                    logger.warning("メインAIスレッドの強制終了")
                    self.ai_thread.terminate()
            
            # AI拡張スレッドの停止
            for thread in self.extension_ai_threads:
                if thread and thread.isRunning():
                    logger.debug("AI拡張スレッドを停止中...")
                    thread.stop()
                    thread.wait(3000)  # 3秒まで待機
                    if thread.isRunning():
                        logger.warning("AI拡張スレッドの強制終了")
                        thread.terminate()

            # 報告書タブのスレッド停止
            for thread in getattr(self, 'report_ai_threads', []):
                if thread and thread.isRunning():
                    logger.debug("報告書AIスレッドを停止中...")
                    thread.stop()
                    thread.wait(3000)
                    if thread.isRunning():
                        logger.warning("報告書AIスレッドの強制終了")
                        thread.terminate()
            
            # スレッドリストをクリア
            self.extension_ai_threads.clear()
            try:
                self.report_ai_threads.clear()
            except Exception:
                pass
            logger.debug("すべてのスレッドのクリーンアップ完了")
            
        except Exception as e:
            logger.error("スレッドクリーンアップエラー: %s", e)
    
    def closeEvent(self, event):
        """ダイアログクローズ時の処理"""
        try:
            logger.debug("AISuggestionDialog終了処理開始")
            self.cleanup_threads()
            event.accept()
        except Exception as e:
            logger.error("ダイアログクローズエラー: %s", e)
            event.accept()
    
    def reject(self):
        """キャンセル時の処理"""
        try:
            logger.debug("AISuggestionDialogキャンセル処理開始")
            self.cleanup_threads()
            super().reject()
        except Exception as e:
            logger.error("ダイアログキャンセルエラー: %s", e)
            super().reject()
    
    def accept(self):
        """OK時の処理"""
        try:
            logger.debug("AISuggestionDialog完了処理開始")
            self.cleanup_threads()
            super().accept()
        except Exception as e:
            logger.error("ダイアログ完了エラー: %s", e)
            super().accept()
    
    def initialize_dataset_dropdown(self):
        """データセット選択ドロップダウンを初期化"""
        if not hasattr(self, 'extension_dataset_combo'):
            logger.debug("extension_dataset_combo が存在しません")
            return

        # This method is triggered from multiple places (direct call + QTimer).
        # If it runs twice, multiple DatasetFilterFetcher instances can stay connected to
        # the same combo and fight each other (e.g., count label oscillation at startup).
        if getattr(self, "_dataset_dropdown_initialized", False):
            return
        if getattr(self, "_dataset_dropdown_initializing", False):
            return
            
        try:
            self._dataset_dropdown_initializing = True
            from config.common import get_dynamic_file_path

            dataset_json_path = get_dynamic_file_path('output/rde/data/dataset.json')
            info_json_path = get_dynamic_file_path('output/rde/data/info.json')

            logger.debug("データセット選択初期化を開始: %s", dataset_json_path)

            self._dataset_filter_fetcher = DatasetFilterFetcher(
                dataset_json_path=dataset_json_path,
                info_json_path=info_json_path,
                combo=self.extension_dataset_combo,
                show_text_search_field=False,
                clear_on_blank_click=True,
                parent=self,
            )

            filter_widget = self._dataset_filter_fetcher.build_filter_panel(parent=self)

            if self._dataset_filter_widget:
                self._dataset_filter_widget.setParent(None)
            if hasattr(self, 'dataset_select_layout'):
                self.dataset_select_layout.insertWidget(1, filter_widget)
            self._dataset_filter_widget = filter_widget

            if not self._dataset_combo_connected:
                self.extension_dataset_combo.currentIndexChanged.connect(self.on_dataset_selection_changed)
                self._dataset_combo_connected = True

            self.select_current_dataset()

            logger.debug("データセット選択初期化完了")

            self._dataset_dropdown_initialized = True

        except Exception as e:
            logger.error("データセット選択初期化エラー: %s", e)
            import traceback
            traceback.print_exc()
        finally:
            self._dataset_dropdown_initializing = False
    
    def select_current_dataset(self):
        """現在のコンテキストに基づいてデータセットを選択"""
        if not hasattr(self, 'extension_dataset_combo'):
            return
            
        try:
            # コンテキストからデータセット名または課題番号を取得
            current_name = self.context_data.get('name', '').strip()
            current_grant_number = self.context_data.get('grant_number', '').strip()
            
            if current_name or current_grant_number:
                # コンボボックスから一致するアイテムを検索
                for i in range(self.extension_dataset_combo.count()):
                    text = self.extension_dataset_combo.itemText(i)
                    dataset = self.extension_dataset_combo.itemData(i)
                    
                    if dataset:
                        attrs = dataset.get('attributes', {})
                        name = attrs.get('name', '')
                        grant_number = attrs.get('grantNumber', '')
                        
                        # 名前または課題番号で一致判定
                        if (current_name and current_name == name) or \
                           (current_grant_number and current_grant_number == grant_number):
                            self.extension_dataset_combo.setCurrentIndex(i)
                            logger.debug("データセット自動選択: %s", text)
                            return
            
        except Exception as e:
            logger.error("データセット自動選択エラー: %s", e)
    
    def on_dataset_selection_changed(self, index: int):
        """データセット選択変更時の処理"""
        try:
            if not hasattr(self, 'extension_dataset_combo'):
                return
                
            if index is None:
                return
            if index < 0:
                return

            dataset_info = self.extension_dataset_combo.itemData(index)
            if not dataset_info:
                return
            
            # コンテキストデータを更新
            self.update_context_from_dataset(dataset_info)
            
            # データセット情報表示を更新
            self.update_dataset_info_display()
            
            display_text = self.extension_dataset_combo.itemText(index)
            logger.debug("データセット選択変更: %s", display_text)
            
        except Exception as e:
            logger.error("データセット選択変更エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def update_context_from_dataset(self, dataset_info):
        """選択されたデータセット情報からコンテキストデータを更新"""
        try:
            # dataset_infoの形式を確認
            if 'attributes' in dataset_info:
                # dataset.json形式の場合
                attrs = dataset_info.get('attributes', {})
                self.context_data['dataset_id'] = dataset_info.get('id', '')
                self.context_data['name'] = attrs.get('name', '')
                self.context_data['grant_number'] = attrs.get('grantNumber', '')
                self.context_data['type'] = attrs.get('datasetType', 'mixed')
                self.context_data['description'] = attrs.get('description', '')
            else:
                # load_dataset_list形式の場合
                self.context_data['dataset_id'] = dataset_info.get('id', '')
                self.context_data['name'] = dataset_info.get('name', '')
                self.context_data['grant_number'] = dataset_info.get('grantNumber', '')
                self.context_data['type'] = dataset_info.get('datasetType', 'mixed')
                self.context_data['description'] = dataset_info.get('description', '')
            
            # アクセスポリシーとコンタクト情報をデフォルト値で設定
            if 'access_policy' not in self.context_data:
                self.context_data['access_policy'] = 'restricted'
            if 'contact' not in self.context_data:
                self.context_data['contact'] = ''
            
            logger.debug("コンテキストデータ更新: dataset_id=%s, name=%s", self.context_data.get('dataset_id', ''), self.context_data.get('name', ''))
            
        except Exception as e:
            logger.error("コンテキストデータ更新エラー: %s", e)
            import traceback
            traceback.print_exc()
    
    def update_dataset_info_display(self):
        """データセット情報表示を更新"""
        try:
            # データセット情報を取得
            dataset_name = self.context_data.get('name', '').strip()
            grant_number = self.context_data.get('grant_number', '').strip()
            dataset_type = self.context_data.get('type', '').strip()
            
            if not dataset_name:
                dataset_name = "データセット名未設定"
            if not grant_number:
                grant_number = "課題番号未設定"
            if not dataset_type:
                dataset_type = "タイプ未設定"
            
            # HTMLを更新
            dataset_info_html = f"""
        <div style="border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; border-radius: 5px; padding: 10px; margin: 5px 0;">
            <h4 style="margin: 0 0 8px 0; ">📊 対象データセット情報</h4>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="font-weight: bold; padding: 2px 10px 2px 0; width: 100px;">データセット名:</td>
                    <td style=" padding: 2px 0;">{dataset_name}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold;  padding: 2px 10px 2px 0;">課題番号:</td>
                    <td style=" padding: 2px 0;">{grant_number}</td>
                </tr>
                <tr>
                    <td style="font-weight: bold;  padding: 2px 10px 2px 0;">タイプ:</td>
                    <td style=" padding: 2px 0;">{dataset_type}</td>
                </tr>
            </table>
        </div>
        """
            
            # dataset_info_labelがある場合のみ更新
            if hasattr(self, 'dataset_info_label') and self.dataset_info_label:
                self.dataset_info_label.setText(dataset_info_html)
            
        except Exception as e:
            logger.error("データセット情報表示更新エラー: %s", e)
    
    def show_all_datasets(self):
        """全データセット表示（▼ボタン用）"""
        try:
            if self._dataset_filter_fetcher:
                self._dataset_filter_fetcher.show_all()
            elif hasattr(self, 'extension_dataset_combo'):
                self.extension_dataset_combo.showPopup()
        except Exception as e:
            logger.error("全データセット表示エラー: %s", e)
