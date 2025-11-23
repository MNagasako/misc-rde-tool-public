"""
AIテスト機能のUI作成とロジック - ARIM RDE Tool v1.17.2
UIControllerから分離したAIテスト機能専用モジュール（リファクタリング版）
"""
import os
import json
import pandas as pd
import logging
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, 
    QComboBox, QTextBrowser, QCompleter, QScrollArea, QCheckBox, 
    QRadioButton, QButtonGroup, QProgressBar, QMessageBox, QDialog,
    QTabWidget
)
from qt_compat.core import QTimer, Qt, QStringListModel
from qt_compat.gui import QFont

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

# ロガー設定
logger = logging.getLogger(__name__)
import datetime

# ダイアログクラスのインポート（リファクタリング後）
from .ai_test_dialogs import PromptTemplateEditorDialog

# 相対インポートを試行、失敗時は直接インポート
try:
    from classes.ui.dialogs.ui_dialogs import TextAreaExpandDialog
    from classes.ui.utilities.ui_utilities import UIUtilities
except ImportError:
    # fallback import for standalone execution
    from classes.ui.dialogs.ui_dialogs import TextAreaExpandDialog
    from classes.ui.utilities.ui_utilities import UIUtilities


def safe_widget_operation(widget, operation, *args, **kwargs):
    """
    ウィジェットに対する操作を安全に実行するヘルパー関数
    
    Args:
        widget: 操作対象のウィジェット
        operation: 実行する操作（関数）
        *args, **kwargs: 操作に渡す引数
        
    Returns:
        操作の結果、エラー時はNone
    """
    if widget is None:
        return None
    
    try:
        # ウィジェットが有効かチェック（親ウィジェットがあるかで判定）
        if widget.parent() is not None:
            return operation(*args, **kwargs)
        else:
            logger.debug("ウィジェット %s は既に削除済みです", widget.__class__.__name__)
            return None
    except RuntimeError as e:
        logger.debug("ウィジェット操作時エラー（削除済み）: %s", e)
        return None


class AITestWidget:
    """AIテスト機能のUI作成とロジックを担当するクラス"""
    
    def __init__(self, parent_controller):
        self.parent_controller = parent_controller
        # リクエスト履歴管理
        self.request_history = []  # 全リクエスト履歴
        self.last_request_content = ""  # 最後のリクエスト内容
        self.last_request_time = ""  # 最後のリクエスト時刻
        
        # パフォーマンス改善：データキャッシュ
        self._cached_experiment_data = None  # 実験データキャッシュ
        self._cached_arim_data = None  # ARIM拡張データキャッシュ
        self._cached_static_data = {}  # 静的ファイルデータキャッシュ
        self._cached_templates = {}  # プロンプトテンプレートキャッシュ
        self._template_file_times = {}  # テンプレートファイルの最終更新時刻
        self._data_source_cache = {}  # データソース別キャッシュ
        self._last_data_source = None  # 最後に使用したデータソース
        
        # デバッグ出力制御
        self._debug_enabled = True  # デバッグ出力を有効化（AIプロバイダ問題調査のため）
        
    def enable_debug_output(self, enabled=True):
        """デバッグ出力の有効/無効を切り替え"""
        self._debug_enabled = enabled
        if enabled:
            logger.debug("AIテスト機能のデバッグ出力が有効になりました")
        
    def clear_cache(self):
        """キャッシュをクリア（パフォーマンステスト用）"""
        self._cached_experiment_data = None
        self._cached_arim_data = None
        self._cached_static_data = {}
        self._cached_templates = {}
        self._template_file_times = {}
        self._data_source_cache = {}
        self._last_data_source = None
        if self._debug_enabled:
            logger.debug("AIテスト機能のキャッシュをクリアしました")
    
    def clear_template_cache(self, template_file=None):
        """テンプレートキャッシュをクリア（テンプレート編集後の反映用）"""
        if template_file:
            # 特定のテンプレートファイルのキャッシュのみクリア
            if template_file in self._cached_templates:
                del self._cached_templates[template_file]
            if template_file in self._template_file_times:
                del self._template_file_times[template_file]
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[DEBUG] テンプレートキャッシュをクリア: {template_file}")
        else:
            # 全テンプレートキャッシュをクリア
            self._cached_templates = {}
            self._template_file_times = {}
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(f"[DEBUG] 全テンプレートキャッシュをクリアしました")
    
    def _measure_performance(self, func_name, func, *args, **kwargs):
        """パフォーマンス計測用デコレーター関数"""
        if self._debug_enabled:
            import time
            start_time = time.time()
            result = func(*args, **kwargs)
            end_time = time.time()
            elapsed = end_time - start_time
            logger.debug("[PERF] %s: %.3f秒", func_name, elapsed)
            return result
        else:
            return func(*args, **kwargs)
        
    def create_widget(self):
        """AIテスト機能用のウィジェットを作成（完全版）"""
        widget = QWidget()
        layout = QVBoxLayout()
        # レイアウトの間隔を設定して要素の重なりを防ぐ
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # タイトル
        self._title_label = QLabel("AI機能テスト")
        self._title_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {get_color(ThemeKey.TEXT_INFO)}; padding: 8px; margin-bottom: 5px;")
        layout.addWidget(self._title_label)
        
        # AI選択エリア（分割されたメソッド使用）
        self._create_ai_selection_area(layout)
        
        # プロンプト入力エリア（分割されたメソッド使用）
        self._create_prompt_input_area(layout)
        
        # プロンプト送信エリア（分割されたメソッド使用）
        self._create_prompt_send_area(layout)
        
        
        # 課題番号選択エリア（分割されたメソッド使用）
        self._create_task_selection_area(layout)
        
        # イベントハンドラーの接続
        # AIプロバイダー変更時の処理を接続
        if hasattr(self, 'ai_provider_combo') and self.ai_provider_combo is not None:
            self._debug_print("[DEBUG] Connecting ai_provider_combo event handlers")
            self.ai_provider_combo.currentTextChanged.connect(lambda text: self.on_ai_provider_changed(text))
        
        if hasattr(self, 'task_id_combo') and self.task_id_combo is not None:
            self._debug_print("[DEBUG] Connecting task_id_combo event handlers")
            self.task_id_combo.currentTextChanged.connect(lambda text: self.on_task_id_changed(text))
            self.task_id_combo.currentIndexChanged.connect(lambda index: self.on_task_index_changed(index))
        
        if hasattr(self, 'task_completer') and self.task_completer:
            self.task_completer.activated.connect(lambda text: self.on_completer_activated(text))
        
        if hasattr(self, 'datasource_button_group') and self.datasource_button_group:
            self.datasource_button_group.buttonClicked.connect(lambda button: self.on_datasource_changed(button))
        
        self.experiment_combo.currentIndexChanged.connect(lambda index: self.on_experiment_changed(index))
        
        # AI分析方法選択エリア（分割されたメソッド使用）
        self._create_analysis_method_area(layout)
        
        # ボタンエリア（分割されたメソッド使用）
        self._create_button_area(layout)
        
        # プログレス表示エリア（分割されたメソッド使用）
        self._create_progress_area(layout)
        
        # レスポンス表示エリア（分割されたメソッド使用）
        self._create_response_area(layout)
        
        widget.setLayout(layout)
        
        # 親コントローラーにAI設定コンポーネントを設定（重要）
        # これにより、UIController及びUIControllerAIからアクセス可能になる
        self.parent_controller.ai_provider_combo = self.ai_provider_combo
        self.parent_controller.ai_model_combo = self.ai_model_combo
        self.parent_controller.ai_prompt_input = self.ai_prompt_input
        self.parent_controller.ai_response_display = self.ai_response_display
        self.parent_controller.ai_result_display = self.ai_result_display
        self.parent_controller.ai_progress_bar = self.ai_progress_bar
        self.parent_controller.ai_progress_label = self.ai_progress_label
        # analysis_method_combo と analysis_description_label は既に設定済み
        
        self._debug_print(f"[DEBUG] AI設定コンポーネントを親コントローラーに設定完了")
        self._debug_print(f"[DEBUG] ai_provider_combo: {self.parent_controller.ai_provider_combo}")
        self._debug_print(f"[DEBUG] ai_model_combo: {self.parent_controller.ai_model_combo}")
        self._debug_print(f"[DEBUG] analysis_method_combo: {self.parent_controller.analysis_method_combo}")
        self._debug_print(f"[DEBUG] analysis_description_label: {self.parent_controller.analysis_description_label}")
        self._debug_print(f"[DEBUG] ai_progress_bar: {self.parent_controller.ai_progress_bar}")
        self._debug_print(f"[DEBUG] ai_progress_label: {self.parent_controller.ai_progress_label}")
        
        # スクロール可能なウィジェットとして設定
        scroll_area = QScrollArea()
        scroll_area.setWidget(widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QScrollBar:vertical {{
                border: none;
                background: {get_color(ThemeKey.SCROLLBAR_BACKGROUND)};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {get_color(ThemeKey.SCROLLBAR_HANDLE)};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {get_color(ThemeKey.SCROLLBAR_HANDLE_HOVER)};
            }}
        """)
        # 後でテーマ更新するため保持
        self._scroll_area = scroll_area
        
        # AI設定を初期化（ウィジェット設定後に遅延実行）
        QTimer.singleShot(100, self._init_ai_settings)
        
        # ウィジェット初期化確認
        self._debug_print(f"[DEBUG] AI test widget created successfully")
        self._debug_print(f"[DEBUG] experiment_combo initialized: {hasattr(self, 'experiment_combo')}")
        if hasattr(self, 'experiment_combo'):
            self._debug_print(f"[DEBUG] experiment_combo type: {type(self.experiment_combo)}")
            self._debug_print(f"[DEBUG] experiment_combo visible: {self.experiment_combo.isVisible()}")
            
        # 初期データ読み込み（ウィジェット作成完了後、遅延を短縮してパフォーマンス向上）
        QTimer.singleShot(100, self._initialize_task_data)  # 1秒から100msに短縮

        # テーマ変更に追従
        try:
            from classes.theme.theme_manager import ThemeManager
            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        except Exception:
            pass

        return scroll_area
    
    def _debug_print(self, message):
        """デバッグ出力（パフォーマンス向上のため制御可能）"""
        if self._debug_enabled:
            print(message)
    
    
    def _create_ai_selection_area(self, layout):
        """AI選択エリアの作成（create_widget分割）"""
        # AI選択エリア
        ai_layout = QHBoxLayout()
        ai_layout.setSpacing(10)
        ai_layout.addWidget(QLabel("AIプロバイダー:"))
        
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.setMinimumWidth(120)
        # AIプロバイダーコンボボックスのフォントサイズ設定
        ai_provider_font = QFont("Yu Gothic UI", 14)
        self.ai_provider_combo.setFont(ai_provider_font)
        self.ai_provider_combo.setStyleSheet("QComboBox { font-size: 14px; padding: 4px; }")
        ai_layout.addWidget(self.ai_provider_combo)
        
        ai_layout.addWidget(QLabel("モデル:"))
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.setMinimumWidth(150)
        # AIモデルコンボボックスのフォントサイズ設定
        ai_model_font = QFont("Yu Gothic UI", 14)
        self.ai_model_combo.setFont(ai_model_font)
        self.ai_model_combo.setStyleSheet("QComboBox { font-size: 14px; padding: 4px; }")
        ai_layout.addWidget(self.ai_model_combo)
        
        # 接続テストボタン
        test_btn = UIUtilities.create_auto_resize_button(
            "接続テスト", 80, 30,
            ""
        )
        test_btn.setProperty("variant", "success")
        test_btn.clicked.connect(lambda: self.test_ai_connection())
        ai_layout.addWidget(test_btn)
        
        ai_layout.addStretch()
        layout.addLayout(ai_layout)
        
    def _create_prompt_input_area(self, layout):
        """プロンプト入力エリアの作成（create_widget分割）"""
        # プロンプト入力欄にマージンを追加
        prompt_label_layout = QHBoxLayout()
        prompt_label = QLabel("プロンプト:")
        prompt_label.setStyleSheet("margin-top: 10px; margin-bottom: 5px;")
        prompt_label_layout.addWidget(prompt_label)
        
        # まず ai_prompt_input を作成
        self.ai_prompt_input = QTextEdit()
        self.ai_prompt_input.setPlaceholderText("ここにプロンプトを入力してください...")
        self.ai_prompt_input.setFixedHeight(80)
        self.ai_prompt_input.setStyleSheet("margin-bottom: 10px;")
        
        # その後でプロンプト用拡大表示ボタンを作成
        prompt_expand_btn = UIUtilities.create_expand_button(self, self.ai_prompt_input, "プロンプト入力")
        prompt_label_layout.addWidget(prompt_expand_btn)
        prompt_label_layout.addStretch()
        layout.addLayout(prompt_label_layout)
        
        layout.addWidget(self.ai_prompt_input)
        
    def _create_prompt_send_area(self, layout):
        """プロンプト送信エリアの作成（create_widget分割）"""
        # プロンプト入力欄直下に送信ボタンを配置
        prompt_send_layout = QHBoxLayout()
        prompt_send_layout.setSpacing(10)
        prompt_send_layout.setContentsMargins(0, 5, 0, 10)
        
        # AI問い合わせボタン（プロンプト専用）
        send_btn = UIUtilities.create_auto_resize_button(
            "AI問い合わせ", 120, 32,
            ""
        )
        send_btn.setProperty("variant", "info")
        send_btn.clicked.connect(lambda: self.send_ai_prompt())
        prompt_send_layout.addWidget(send_btn)
        prompt_send_layout.addStretch()  # 右側にスペースを追加
        layout.addLayout(prompt_send_layout)
        
    def _create_task_selection_area(self, layout):
        """課題番号選択エリアの作成（create_widget分割）"""

        # === ルートレイアウト ===
        task_layout = QVBoxLayout()
        task_layout.setSpacing(8)

        # === 見出し＋更新ボタン行 ===
        task_label_layout = QHBoxLayout()
        task_label_layout.setSpacing(10)

        task_label = QLabel("課題番号（MI分析用）:")
        task_label.setStyleSheet("margin-top: 5px;")
        task_label_layout.addWidget(task_label)

        refresh_btn = UIUtilities.create_auto_resize_button(
            "更新", 60, 24,
            ""
        )
        refresh_btn.setProperty("variant", "success")
        refresh_btn.clicked.connect(lambda: self.refresh_task_ids())
        task_label_layout.addWidget(refresh_btn)
        task_label_layout.addStretch()
        task_layout.addLayout(task_label_layout)

        # === 課題番号コンボ（検索・補完） ===
        task_combo_layout = QHBoxLayout()

        self.task_id_combo = QComboBox()
        self.task_id_combo.setEditable(True)                          # 検索有効化
        self.task_id_combo.setInsertPolicy(QComboBox.NoInsert)        # 新規項目追加なし
        self.task_id_combo.setMinimumWidth(600)
        self.task_id_combo.setMaximumWidth(800)

        task_combo_font = QFont("Yu Gothic UI", 11)
        self.task_id_combo.setFont(task_combo_font)
        self.task_id_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 5px;
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 4px;
                font-size: 12px;
            }}
            QComboBox::drop-down {{ border: none; background: {get_color(ThemeKey.COMBO_DROPDOWN_BACKGROUND)}; }}
            QComboBox::down-arrow {{ width: 12px; height: 12px; }}
        """)

        # オートコンプリート設定
        self.task_completer = QCompleter()
        self.task_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.task_completer.setFilterMode(Qt.MatchContains)  # 部分一致

        completer_model = QStringListModel([])  # 空モデルで初期化
        self.task_completer.setModel(completer_model)
        self.task_id_combo.setCompleter(self.task_completer)

        task_combo_layout.addWidget(self.task_id_combo)
        task_combo_layout.addStretch()
        task_layout.addLayout(task_combo_layout)

        # === 課題情報表示 ===
        task_info_layout = QVBoxLayout()
        task_info_layout.setSpacing(5)

        task_info_header_layout = QHBoxLayout()
        task_info_header_layout.setSpacing(10)

        self._task_info_title_label = QLabel("選択した課題の詳細情報:")
        self._task_info_title_label.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.TEXT_SECONDARY)}; font-size: 14px;")
        task_info_header_layout.addWidget(self._task_info_title_label)

        self._task_info_expand_btn = QPushButton("🔍")
        self._task_info_expand_btn.setToolTip("課題詳細情報を拡大表示")
        self._task_info_expand_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_EXPAND_BACKGROUND)};
                border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                border-radius: 12px;
                width: 24px; height: 24px;
                font-size: 12px; color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
            }}
            QPushButton:hover {{ background-color: {get_color(ThemeKey.MENU_ITEM_BACKGROUND_HOVER)}; }}
            QPushButton:pressed {{ background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; }}
        """)
        self._task_info_expand_btn.setMaximumSize(24, 24)
        self._task_info_expand_btn.setMinimumSize(24, 24)
        self._task_info_expand_btn.clicked.connect(lambda: self.show_task_info_popup())
        task_info_header_layout.addWidget(self._task_info_expand_btn)
        task_info_header_layout.addStretch()

        task_info_layout.addLayout(task_info_header_layout)

        self.task_info_label = QLabel("課題番号を選択してください")
        self.task_info_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 14px; padding: 8px; "
            f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; border-radius: 3px; margin-top: 5px; border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};"
        )
        self.task_info_label.setWordWrap(True)
        self.task_info_label.setMinimumHeight(80)
        self.task_info_label.setAlignment(Qt.AlignTop)
        task_info_layout.addWidget(self.task_info_label)

        task_layout.addLayout(task_info_layout)

        # === データソース選択 ===
        datasource_layout = QVBoxLayout()
        datasource_layout.setSpacing(8)

        self._datasource_label = QLabel("実験データソース:")
        self._datasource_label.setStyleSheet("margin-top: 10px; font-weight: bold;")
        datasource_layout.addWidget(self._datasource_label)

        datasource_radio_layout = QHBoxLayout()
        datasource_radio_layout.setSpacing(15)
        datasource_radio_layout.setContentsMargins(10, 5, 0, 5)

        self.datasource_button_group = QButtonGroup()

        self.arim_exp_radio = QRadioButton("ARIM実験データ (arim_exp.xlsx)")
        self.arim_exp_radio.setStyleSheet(f"font-size: 14px; color: {get_color(ThemeKey.TEXT_SECONDARY)};")
        self.datasource_button_group.addButton(self.arim_exp_radio, 0)
        datasource_radio_layout.addWidget(self.arim_exp_radio)

        self.normal_exp_radio = QRadioButton("標準実験データ (exp.xlsx)")
        self.normal_exp_radio.setStyleSheet(f"font-size: 14px; color: {get_color(ThemeKey.TEXT_SECONDARY)};")
        self.datasource_button_group.addButton(self.normal_exp_radio, 1)
        datasource_radio_layout.addWidget(self.normal_exp_radio)

        datasource_radio_layout.addStretch()
        datasource_layout.addLayout(datasource_radio_layout)

        self.datasource_info_label = QLabel("")
        self.datasource_info_label.setStyleSheet(
            f"color: {get_color(ThemeKey.INPUT_TEXT)}; font-size: 14px; padding: 5px; "
            f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; border-radius: 3px; margin-top: 3px;"
        )
        self.datasource_info_label.setWordWrap(True)
        datasource_layout.addWidget(self.datasource_info_label)

        task_layout.addLayout(datasource_layout)

        # === 実験データ選択（単体分析用） ===
        experiment_layout = QVBoxLayout()

        experiment_label = QLabel("実験データ選択（単体分析用）:")
        experiment_layout.addWidget(experiment_label)

        self.experiment_combo = QComboBox()
        self.experiment_combo.setMinimumWidth(600)
        self.experiment_combo.setMaximumWidth(800)

        experiment_combo_font = QFont("Yu Gothic UI", 14)
        self.experiment_combo.setFont(experiment_combo_font)
        self.experiment_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 5px;
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 4px;
                font-size: 12px;
            }}
            QComboBox::drop-down {{ border: none; background: {get_color(ThemeKey.COMBO_DROPDOWN_BACKGROUND)}; }}
        """)

        # 初期プレースホルダー
        self.experiment_combo.addItem("課題番号を選択してください", None)
        self.experiment_combo.setVisible(True)
        experiment_layout.addWidget(self.experiment_combo)

        # 実験データ詳細表示
        experiment_info_layout = QVBoxLayout()
        experiment_info_layout.setSpacing(5)

        experiment_info_header_layout = QHBoxLayout()
        experiment_info_header_layout.setSpacing(10)

        self._experiment_info_title_label = QLabel("選択した実験データの詳細情報:")
        self._experiment_info_title_label.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.TEXT_SECONDARY)}; font-size: 14px;")
        experiment_info_header_layout.addWidget(self._experiment_info_title_label)

        self._experiment_info_expand_btn = QPushButton("🔍")
        self._experiment_info_expand_btn.setToolTip("実験データ詳細情報を拡大表示")
        self._experiment_info_expand_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_EXPAND_BACKGROUND)};
                border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                border-radius: 12px;
                width: 24px; height: 24px;
                font-size: 12px; color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
            }}
            QPushButton:hover {{ background-color: {get_color(ThemeKey.MENU_ITEM_BACKGROUND_HOVER)}; }}
            QPushButton:pressed {{ background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; }}
        """)
        self._experiment_info_expand_btn.setMaximumSize(24, 24)
        self._experiment_info_expand_btn.setMinimumSize(24, 24)
        self._experiment_info_expand_btn.clicked.connect(lambda: self.show_experiment_info_popup())
        experiment_info_header_layout.addWidget(self._experiment_info_expand_btn)
        experiment_info_header_layout.addStretch()

        experiment_info_layout.addLayout(experiment_info_header_layout)

        self.experiment_info_label = QLabel("課題番号を選択すると、該当する実験データが表示されます。")
        self.experiment_info_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 14px; padding: 12px; background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; "
            f"border-radius: 3px; margin-top: 5px; border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};"
        )
        self.experiment_info_label.setWordWrap(True)
        self.experiment_info_label.setMinimumHeight(150)
        self.experiment_info_label.setMaximumHeight(250)
        self.experiment_info_label.setAlignment(Qt.AlignTop)
        self.experiment_info_label.setVisible(True)
        experiment_info_layout.addWidget(self.experiment_info_label)

        experiment_layout.addLayout(experiment_info_layout)
        task_layout.addLayout(experiment_layout)

        # === ARIM拡張情報チェック ===
        arim_extension_layout = QHBoxLayout()
        arim_extension_layout.setSpacing(10)
        arim_extension_layout.setContentsMargins(0, 10, 0, 5)

        self.arim_extension_checkbox = QCheckBox("ARIM拡張情報を使用")
        self.arim_extension_checkbox.setStyleSheet(f"""
            QCheckBox {{
                font-size: 14px;
                color: {get_color(ThemeKey.TEXT_SECONDARY)};
                spacing: 8px;
            }}
            QCheckBox::indicator {{ width: 16px; height: 16px; }}
            QCheckBox::indicator:unchecked {{
                border: 2px solid {get_color(ThemeKey.INPUT_BORDER_DISABLED)}; border-radius: 3px; background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};
            }}
            QCheckBox::indicator:checked {{
                border: 2px solid {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; border-radius: 3px; background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iMTIiIHZpZXdCb3g9IjAgMCAxMiAxMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTIgNkw0LjUgOC41TDEwIDMiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Rya2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KPC9zdmc+Cg==);
            }}
        """)
        self.arim_extension_checkbox.setChecked(True)
        arim_extension_layout.addWidget(self.arim_extension_checkbox)

        self._arim_info_label = QLabel("(input/ai/arim/converted.xlsxからARIMNOで結合)")
        self._arim_info_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 14px; font-style: italic;")
        arim_extension_layout.addWidget(self._arim_info_label)

        arim_extension_layout.addStretch()
        task_layout.addLayout(arim_extension_layout)

        # === ルートに追加 ===
        layout.addLayout(task_layout)

        
    def _create_analysis_method_area(self, layout):
        """AI分析方法選択エリアの作成（create_widget分割）"""
        # === レイアウト土台 ===
        analysis_layout = QVBoxLayout()
        analysis_layout.setSpacing(8)
        analysis_layout.setContentsMargins(0, 15, 0, 10)

        # タイトル
        analysis_label = QLabel("🔬 AI分析方法:")
        analysis_label.setStyleSheet(
            f"font-weight: bold; color: {get_color(ThemeKey.TEXT_INFO)}; margin-bottom: 5px; font-size: 14px;"
        )
        analysis_layout.addWidget(analysis_label)

        # === コンボ＋説明の横並び ===
        analysis_combo_layout = QHBoxLayout()
        analysis_combo_layout.setSpacing(10)

        # コンボボックス
        self.analysis_method_combo = QComboBox()
        self.analysis_method_combo.setMinimumWidth(300)
        self.analysis_method_combo.setMaximumWidth(500)

        # 追加する分析方法オプション（元ロジックを保持）
        analysis_methods = [
            (
                "SINGLE",
                "MI分析（単体）",
                "material_index.txt",
                "選択された実験データ単体でマテリアルインデックス分析を実行",
                ["prepare_exp_info", "prepare_exp_info_ext"],
                ["MI.json"],
            ),
            (
                "MULTI",
                "MI分析（一括）",
                "material_index.txt",
                "一括でマテリアルインデックス分析を実行",
                ["prepare_exp_info", "prepare_exp_info_ext"],
                ["MI.json"],
            ),
            (
                "SINGLE",
                "データセット説明",
                "dataset_explanation.txt",
                "データセットの詳細説明を生成",
                ["prepare_exp_info", "prepare_exp_info_ext"],
                [],
            ),
            (
                "SINGLE",
                "実験手法分析",
                "experiment_method.txt",
                "実験手法と装置の詳細分析を実行",
                ["prepare_exp_info", "prepare_device_info"],
                ["device_specs.json", "method_categories.json"],
            ),
            (
                "MULTI",
                "品質評価（一括）",
                "quality_assessment.txt",
                "全実験データの品質評価を一括実行",
                ["prepare_exp_info", "prepare_quality_metrics"],
                ["quality_standards.json", "evaluation_criteria.json"],
            ),
        ]

        # コンボアイテムを投入（データペイロード含む）
        for exec_type, name, prompt_file, description, data_methods, static_files in analysis_methods:
            self.analysis_method_combo.addItem(
                name,
                {
                    "exec_type": exec_type,
                    "prompt_file": prompt_file,
                    "description": description,
                    "data_methods": data_methods,
                    "static_files": static_files,
                },
            )

        # フォント/スタイル（元の指定を維持）
        analysis_method_font = QFont("Yu Gothic UI", 14)
        self.analysis_method_combo.setFont(analysis_method_font)
        self.analysis_method_combo.setStyleSheet(
            f"""
            QComboBox {{
                padding: 8px;
                border: 2px solid {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                border-radius: 6px;
                font-size: 12px;
                background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};
            }}
            QComboBox::drop-down {{
                border: none;
                background: {get_color(ThemeKey.BUTTON_EXPAND_BACKGROUND)};
            }}
            QComboBox::down-arrow {{
                width: 12px;
                height: 12px;
            }}
            """
        )
        analysis_combo_layout.addWidget(self.analysis_method_combo)

        # プロンプトテンプレート編集ボタンを追加
        self.prompt_edit_button = QPushButton("📝")
        self.prompt_edit_button.setFixedSize(40, 34)
        self.prompt_edit_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND)};
                border: 2px solid {get_color(ThemeKey.BUTTON_NEUTRAL_BORDER)};
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
                color: {get_color(ThemeKey.BUTTON_NEUTRAL_TEXT)};
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_EXPAND_BACKGROUND)};
                border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.MENU_ITEM_BACKGROUND_HOVER)};
            }}
            """
        )
        self.prompt_edit_button.setToolTip("選択された分析方法のプロンプトテンプレートを編集")
        self.prompt_edit_button.clicked.connect(self.open_prompt_template_editor)
        analysis_combo_layout.addWidget(self.prompt_edit_button)

        # === デフォルト選択は「MI分析（単体）」 ===
        default_index = -1
        for i in range(self.analysis_method_combo.count()):
            item_text = self.analysis_method_combo.itemText(i)
            self._debug_print(f"[DEBUG] 分析方法コンボボックス項目 {i}: '{item_text}'")
            if "MI分析（単体）" in item_text:
                default_index = i
                self.analysis_method_combo.setCurrentIndex(i)
                self._debug_print(f"[DEBUG] デフォルト選択設定完了: インデックス {i} - '{item_text}'")
                break

        if default_index == -1:
            self._debug_print("[DEBUG] MI分析（単体）が見つかりませんでした。利用可能な項目:")
            if self._debug_enabled:
                for i in range(self.analysis_method_combo.count()):
                    logger.debug("  [%s] %s", i, self.analysis_method_combo.itemText(i))

        # 説明ラベルを先に作成（デフォルト値で初期化）
        self.analysis_description_label = QLabel("一括でマテリアルインデックス分析を実行")
        self.analysis_description_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 14px; font-style: italic; margin-left: 10px;"
        )
        self.analysis_description_label.setWordWrap(True)
        analysis_combo_layout.addWidget(self.analysis_description_label)

        # 親コントローラーに分析関連コンポーネントを即座に設定
        self.parent_controller.analysis_method_combo = self.analysis_method_combo
        self.parent_controller.analysis_description_label = self.analysis_description_label
        self._debug_print(f"[DEBUG] analysis_method_combo and analysis_description_label set to parent_controller")

        # デフォルト選択時の説明ラベルを更新
        if default_index >= 0:
            self._debug_print(f"[DEBUG] Updating default analysis method description for index: {default_index}")
            self.on_analysis_method_changed(default_index)

        # 余白伸長
        analysis_combo_layout.addStretch()
        analysis_layout.addLayout(analysis_combo_layout)

        # 変更イベント接続（元のラムダ式のまま）
        self.analysis_method_combo.currentIndexChanged.connect(
            lambda index: self.on_analysis_method_changed(index)
        )

        # 親レイアウトへ追加
        layout.addLayout(analysis_layout)

        
    def _create_button_area(self, layout):
        """ボタンエリアの作成（create_widget分割）"""
        # ボタンレイアウト（マージンとスペーシングを追加）
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)  # ボタン間のスペースを増やす
        button_layout.setContentsMargins(0, 15, 0, 10)  # 上下にマージンを追加
        
        # AI分析実行ボタン（統合ボタン）
        ai_analysis_btn = UIUtilities.create_auto_resize_button(
            "🔬 AI分析実行", 120, 32,
            ""
        )
        ai_analysis_btn.setProperty("variant", "secondary")
        ai_analysis_btn.clicked.connect(lambda: self.execute_ai_analysis())
        button_layout.addWidget(ai_analysis_btn)
        
        # ARIM拡張情報表示ボタン
        arim_info_btn = UIUtilities.create_auto_resize_button(
            "ARIM拡張情報", 100, 32,
            ""
        )
        arim_info_btn.setProperty("variant", "warning")
        arim_info_btn.clicked.connect(lambda: self.show_arim_extension_popup())
        button_layout.addWidget(arim_info_btn)
        
        # リクエスト表示ボタン
        request_info_btn = UIUtilities.create_auto_resize_button(
            "リクエスト表示", 100, 32,
            ""
        )
        request_info_btn.setProperty("variant", "bluegrey")
        request_info_btn.clicked.connect(lambda: self.show_request_popup())
        button_layout.addWidget(request_info_btn)
        
        # レスポンス表示ボタン（既存のポップアップ表示）
        response_info_btn = UIUtilities.create_auto_resize_button(
            "レスポンス表示", 100, 32,
            ""
        )
        response_info_btn.setProperty("variant", "success")
        response_info_btn.clicked.connect(lambda: self.show_response_popup())
        button_layout.addWidget(response_info_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
    def _create_progress_area(self, layout):
        """プログレス表示エリアの作成（create_widget分割）"""
        # プログレス表示エリア
        progress_layout = QVBoxLayout()
        
        # プログレスバー
        self.ai_progress_bar = QProgressBar()
        self.ai_progress_bar.setVisible(False)  # 初期状態は非表示
        self.ai_progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 2px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
            }}
            QProgressBar::chunk {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                border-radius: 3px;
            }}
        """)
        progress_layout.addWidget(self.ai_progress_bar)
        
        # プログレス情報ラベル
        self.ai_progress_label = QLabel("")
        self.ai_progress_label.setVisible(False)  # 初期状態は非表示
        self.ai_progress_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 11px; padding: 5px; text-align: center;")
        self.ai_progress_label.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.ai_progress_label)
        
        layout.addLayout(progress_layout)
        
    def _create_response_area(self, layout):
        """レスポンス表示エリアの作成（create_widget分割）"""
        # レスポンス表示欄を2つに分離（マージンを追加）
        # 1. ログ・DEBUG・JSON表示欄
        log_label_layout = QHBoxLayout()
        log_label = QLabel("レスポンス（ログ・DEBUG・JSON）:")
        log_label.setStyleSheet("margin-top: 15px; margin-bottom: 5px; font-weight: bold;")
        log_label_layout.addWidget(log_label)
        
        # まず ai_response_display を作成
        self.ai_response_display = QTextBrowser()
        self.ai_response_display.setPlaceholderText("ログ、DEBUG情報、JSONデータがここに表示されます...")
        font = QFont("Consolas", 9)
        self.ai_response_display.setFont(font)
        self.ai_response_display.setMaximumHeight(200)  # 高さを制限
        self.ai_response_display.setStyleSheet(f"margin-bottom: 10px; border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; border-radius: 4px;")
        
        # その後でログ表示用拡大表示ボタンを作成
        log_expand_btn = UIUtilities.create_expand_button(self, self.ai_response_display, "レスポンス（ログ・DEBUG・JSON）")
        log_label_layout.addWidget(log_expand_btn)
        log_label_layout.addStretch()
        layout.addLayout(log_label_layout)
        
        layout.addWidget(self.ai_response_display)
        
        # 2. 問い合わせ結果表示欄（別枠）
        result_label_layout = QHBoxLayout()
        result_label = QLabel("問い合わせ結果:")
        result_label.setStyleSheet("margin-bottom: 5px; font-weight: bold;")
        result_label_layout.addWidget(result_label)
        
        # まず ai_result_display を作成
        self.ai_result_display = QTextBrowser()
        self.ai_result_display.setPlaceholderText("AIからの回答結果がここに表示されます...")
        result_font = QFont("Yu Gothic UI", 10)
        self.ai_result_display.setFont(result_font)
        self.ai_result_display.setMinimumHeight(150)
        self.ai_result_display.setStyleSheet(f"border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; border-radius: 4px; margin-bottom: 10px;")
        
        # その後で結果表示用拡大表示ボタンを作成
        result_expand_btn = UIUtilities.create_expand_button(self, self.ai_result_display, "問い合わせ結果")
        result_label_layout.addWidget(result_expand_btn)
        result_label_layout.addStretch()
        layout.addLayout(result_label_layout)
        
        layout.addWidget(self.ai_result_display)

    def refresh_theme(self, *_):
        """テーマ変更時に必要なスタイルを再適用する"""
        try:
            # タイトル
            if hasattr(self, '_title_label') and self._title_label:
                self._title_label.setStyleSheet(
                    f"font-size: 14px; font-weight: bold; color: {get_color(ThemeKey.TEXT_INFO)}; padding: 8px; margin-bottom: 5px;"
                )

            # コンボボックス類
            if hasattr(self, 'task_id_combo') and self.task_id_combo:
                self.task_id_combo.setStyleSheet(
                    f"""
                    QComboBox {{
                        padding: 5px;
                        border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                        border-radius: 4px;
                        font-size: 12px;
                    }}
                    QComboBox::drop-down {{ border: none; background: {get_color(ThemeKey.COMBO_DROPDOWN_BACKGROUND)}; }}
                    QComboBox::down-arrow {{ width: 12px; height: 12px; }}
                    """
                )
            if hasattr(self, 'experiment_combo') and self.experiment_combo:
                self.experiment_combo.setStyleSheet(
                    f"""
                    QComboBox {{
                        padding: 5px;
                        border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                        border-radius: 4px;
                        font-size: 12px;
                    }}
                    QComboBox::drop-down {{ border: none; background: {get_color(ThemeKey.COMBO_DROPDOWN_BACKGROUND)}; }}
                    """
                )

            # 情報見出しラベル
            if hasattr(self, '_task_info_title_label') and self._task_info_title_label:
                self._task_info_title_label.setStyleSheet(
                    f"font-weight: bold; color: {get_color(ThemeKey.TEXT_SECONDARY)}; font-size: 14px;"
                )
            if hasattr(self, '_experiment_info_title_label') and self._experiment_info_title_label:
                self._experiment_info_title_label.setStyleSheet(
                    f"font-weight: bold; color: {get_color(ThemeKey.TEXT_SECONDARY)}; font-size: 14px;"
                )

            # 情報ラベルの本体
            if hasattr(self, 'task_info_label') and self.task_info_label:
                self.task_info_label.setStyleSheet(
                    f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 14px; padding: 8px; "
                    f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; border-radius: 3px; margin-top: 5px; border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};"
                )
            if hasattr(self, 'experiment_info_label') and self.experiment_info_label:
                self.experiment_info_label.setStyleSheet(
                    f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 14px; padding: 12px; background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; "
                    f"border-radius: 3px; margin-top: 5px; border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};"
                )

            # 拡大ボタン
            if hasattr(self, '_task_info_expand_btn') and self._task_info_expand_btn:
                self._task_info_expand_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_EXPAND_BACKGROUND)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                        border-radius: 12px;
                        width: 24px; height: 24px;
                        font-size: 12px; color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    }}
                    QPushButton:hover {{ background-color: {get_color(ThemeKey.MENU_ITEM_BACKGROUND_HOVER)}; }}
                    QPushButton:pressed {{ background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; }}
                    """
                )
            if hasattr(self, '_experiment_info_expand_btn') and self._experiment_info_expand_btn:
                self._experiment_info_expand_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_EXPAND_BACKGROUND)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                        border-radius: 12px;
                        width: 24px; height: 24px;
                        font-size: 12px; color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    }}
                    QPushButton:hover {{ background-color: {get_color(ThemeKey.MENU_ITEM_BACKGROUND_HOVER)}; }}
                    QPushButton:pressed {{ background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; }}
                    """
                )

            # データソース関連
            if hasattr(self, 'arim_exp_radio') and self.arim_exp_radio:
                self.arim_exp_radio.setStyleSheet(f"font-size: 14px; color: {get_color(ThemeKey.TEXT_SECONDARY)};")
            if hasattr(self, 'normal_exp_radio') and self.normal_exp_radio:
                self.normal_exp_radio.setStyleSheet(f"font-size: 14px; color: {get_color(ThemeKey.TEXT_SECONDARY)};")
            if hasattr(self, 'datasource_info_label') and self.datasource_info_label:
                self.datasource_info_label.setStyleSheet(
                    f"color: {get_color(ThemeKey.INPUT_TEXT)}; font-size: 14px; padding: 5px; "
                    f"background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; border-radius: 3px; margin-top: 3px;"
                )

            # ARIM拡張チェック
            if hasattr(self, 'arim_extension_checkbox') and self.arim_extension_checkbox:
                self.arim_extension_checkbox.setStyleSheet(
                    f"""
                    QCheckBox {{
                        font-size: 14px;
                        color: {get_color(ThemeKey.TEXT_SECONDARY)};
                        spacing: 8px;
                    }}
                    QCheckBox::indicator {{ width: 16px; height: 16px; }}
                    QCheckBox::indicator:unchecked {{
                        border: 2px solid {get_color(ThemeKey.INPUT_BORDER_DISABLED)}; border-radius: 3px; background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};
                    }}
                    QCheckBox::indicator:checked {{
                        border: 2px solid {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; border-radius: 3px; background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                        image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iMTIiIHZpZXdCb3g9IjAgMCAxMiAxMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTIgNkw0LjUgOC41TDEwIDMiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Rya2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KPC9zdmc+Cg==);
                    }}
                    """
                )
            if hasattr(self, '_arim_info_label') and self._arim_info_label:
                self._arim_info_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 14px; font-style: italic;")

            # 分析方法コンボ/説明
            if hasattr(self, 'analysis_method_combo') and self.analysis_method_combo:
                self.analysis_method_combo.setStyleSheet(
                    f"""
                    QComboBox {{
                        padding: 8px;
                        border: 2px solid {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                        border-radius: 6px;
                        font-size: 12px;
                        background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};
                    }}
                    QComboBox::drop-down {{
                        border: none;
                        background: {get_color(ThemeKey.BUTTON_EXPAND_BACKGROUND)};
                    }}
                    QComboBox::down-arrow {{
                        width: 12px;
                        height: 12px;
                    }}
                    """
                )
            if hasattr(self, 'analysis_description_label') and self.analysis_description_label:
                self.analysis_description_label.setStyleSheet(
                    f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 14px; font-style: italic; margin-left: 10px;"
                )

            if hasattr(self, 'prompt_edit_button') and self.prompt_edit_button:
                self.prompt_edit_button.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND)};
                        border: 2px solid {get_color(ThemeKey.BUTTON_NEUTRAL_BORDER)};
                        border-radius: 6px;
                        font-size: 16px;
                        font-weight: bold;
                        color: {get_color(ThemeKey.BUTTON_NEUTRAL_TEXT)};
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_EXPAND_BACKGROUND)};
                        border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    }}
                    QPushButton:pressed {{
                        background-color: {get_color(ThemeKey.MENU_ITEM_BACKGROUND_HOVER)};
                    }}
                    """
                )

            # プログレス
            if hasattr(self, 'ai_progress_bar') and self.ai_progress_bar:
                self.ai_progress_bar.setStyleSheet(
                    f"""
                    QProgressBar {{
                        border: 2px solid {get_color(ThemeKey.BORDER_DEFAULT)};
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
            if hasattr(self, 'ai_progress_label') and self.ai_progress_label:
                self.ai_progress_label.setStyleSheet(
                    f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 11px; padding: 5px; text-align: center;"
                )

            # レスポンス表示
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.setStyleSheet(
                    f"margin-bottom: 10px; border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; border-radius: 4px;"
                )
            if hasattr(self, 'ai_result_display') and self.ai_result_display:
                self.ai_result_display.setStyleSheet(
                    f"border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; border-radius: 4px; margin-bottom: 10px;"
                )

            # スクロールバー
            if hasattr(self, '_scroll_area') and self._scroll_area:
                self._scroll_area.setStyleSheet(
                    f"""
                    QScrollArea {{
                        border: none;
                        background-color: transparent;
                    }}
                    QScrollBar:vertical {{
                        border: none;
                        background: {get_color(ThemeKey.SCROLLBAR_BACKGROUND)};
                        width: 12px;
                        border-radius: 6px;
                    }}
                    QScrollBar::handle:vertical {{
                        background: {get_color(ThemeKey.SCROLLBAR_HANDLE)};
                        border-radius: 6px;
                        min-height: 20px;
                    }}
                    QScrollBar::handle:vertical:hover {{
                        background: {get_color(ThemeKey.SCROLLBAR_HANDLE_HOVER)};
                    }}
                    """
                )
        except Exception as e:
            logger.debug("refresh_theme failed: %s", e)

    def _get_ai_controller_with_setup(self):
        """AIコントローラーを取得し、必要な設定を行う共通ヘルパー"""
        try:
            # メインのUIControllerAIインスタンスを取得
            if not (hasattr(self.parent_controller, 'ai_controller') and self.parent_controller.ai_controller):
                self.ai_response_display.append("[ERROR] メインのAIコントローラーが見つかりません")
                return None
            
            ai_controller = self.parent_controller.ai_controller
            
            # UIControllerAIのウィジェット設定を確実に行う
            ai_controller.setup_ai_widgets(
                ai_response_display=self.ai_response_display,
                ai_result_display=self.ai_result_display if hasattr(self, 'ai_result_display') else None,
                ai_provider_combo=self.ai_provider_combo if hasattr(self, 'ai_provider_combo') else None
            )
            
            # 必要な情報を直接設定
            ai_controller.parent.analysis_method_combo = self.analysis_method_combo if hasattr(self, 'analysis_method_combo') else None
            ai_controller.parent.analysis_description_label = self.analysis_description_label if hasattr(self, 'analysis_description_label') else None
            ai_controller.parent.ai_progress_bar = self.ai_progress_bar if hasattr(self, 'ai_progress_bar') else None
            ai_controller.parent.ai_progress_label = self.ai_progress_label if hasattr(self, 'ai_progress_label') else None
            ai_controller.parent.task_id_combo = self.task_id_combo if hasattr(self, 'task_id_combo') else None
            ai_controller.parent.experiment_combo = self.experiment_combo if hasattr(self, 'experiment_combo') else None
            ai_controller.parent.arim_extension_checkbox = self.arim_extension_checkbox if hasattr(self, 'arim_extension_checkbox') else None
            
            return ai_controller
            
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] AIコントローラー設定エラー: {e}")
            import traceback
            self.ai_response_display.append(f"[DEBUG] Traceback: {traceback.format_exc()}")
            return None
    
    def _execute_analysis_common(self, method_name, prompt_file, data_methods, static_files, is_batch=False):
        """共通分析実行処理（重複パターン統合）"""
        try:
            import json
            import os
            from config.common import get_dynamic_file_path
            
            self.ai_response_display.append(f"[INFO] {method_name}を実行中...")
            self.ai_response_display.append(f"[DEBUG] データ取得メソッド: {data_methods}")
            
            # プロンプトテンプレート読み込み
            prompt_template = self._load_prompt_template(prompt_file)
            if not prompt_template:
                self.ai_response_display.append("[ERROR] プロンプトテンプレートの読み込みに失敗しました")
                return
            
            # データ準備メソッドを使用してデータを取得
            experiment_data = {}
            if data_methods:
                for method_name_data in data_methods:
                    self.ai_response_display.append(f"[DEBUG] データ準備メソッド実行: {method_name_data}")
                    if hasattr(self, method_name_data):
                        method = getattr(self, method_name_data)
                        method_data = method()
                        experiment_data.update(method_data)
                        self.ai_response_display.append(f"[DEBUG] {method_name_data} 完了: {len(method_data)}件のデータ")
                    else:
                        self.ai_response_display.append(f"[WARNING] データ準備メソッド {method_name_data} が見つかりません")
            
            if not experiment_data:
                self.ai_response_display.append("[ERROR] 実験データの準備に失敗しました")
                return
                
            # 静的データの読み込み
            static_data = {}
            if static_files:
                for static_file in static_files:
                    static_path = get_dynamic_file_path(f"input/ai/{static_file}")
                    if os.path.exists(static_path):
                        try:
                            with open(static_path, 'r', encoding='utf-8') as f:
                                static_data[static_file] = json.load(f)
                            self.ai_response_display.append(f"[DEBUG] 静的データ読み込み完了: {static_file}")
                        except Exception as e:
                            self.ai_response_display.append(f"[WARNING] 静的データ読み込みエラー {static_file}: {e}")
                    else:
                        self.ai_response_display.append(f"[WARNING] 静的データファイルが見つかりません: {static_file}")
            
            # プロンプト構築
            # UIControllerAIと互換性のあるprepared_dataを生成
            prepared_data = None
            checkbox_checked = hasattr(self, 'arim_extension_checkbox') and self.arim_extension_checkbox.isChecked()
            
            self.ai_response_display.append(f"[DEBUG] AITestWidget プロンプト構築開始")
            self.ai_response_display.append(f"[DEBUG] AITestWidget ARIM拡張チェックボックス: {checkbox_checked}")
            self.ai_response_display.append(f"[DEBUG] AITestWidget data_methods: {data_methods}")
            
            if checkbox_checked:
                # UIControllerのdata_methodsを利用してprepared_dataを生成
                ai_controller = self._get_ai_controller_with_setup()
                if ai_controller and ai_controller.parent and data_methods:
                    try:
                        prepared_data = {}
                        selected_task_id = None
                        if hasattr(self, 'task_selector') and self.task_selector.currentData():
                            selected_task_id = self.task_selector.currentData().get('id')
                        
                        self.ai_response_display.append(f"[DEBUG] AITestWidget 選択された課題ID: {selected_task_id}")
                        
                        if selected_task_id:
                            self.ai_response_display.append(f"[DEBUG] AITestWidget UIController data_methodsを使用してprepared_data生成開始")
                            for method_name_str in data_methods:
                                if hasattr(ai_controller.parent, method_name_str):
                                    method = getattr(ai_controller.parent, method_name_str)
                                    self.ai_response_display.append(f"[DEBUG] AITestWidget {method_name_str} 実行開始")
                                    method_result = method(selected_task_id, experiment_data)
                                    if method_result:
                                        prepared_data[method_name_str] = method_result
                                        self.ai_response_display.append(f"[DEBUG] AITestWidget {method_name_str} 生成完了: {len(method_result)} 文字")
                                        # prepare_exp_info_extの内容を確認
                                        if method_name_str == 'prepare_exp_info_ext':
                                            self.ai_response_display.append(f"[DEBUG] AITestWidget prepare_exp_info_ext 内容確認: {method_result[:200]}...")
                                    else:
                                        self.ai_response_display.append(f"[DEBUG] AITestWidget {method_name_str} 生成結果なし")
                                else:
                                    self.ai_response_display.append(f"[WARNING] AITestWidget メソッド {method_name_str} が見つかりません")
                            
                            self.ai_response_display.append(f"[DEBUG] AITestWidget prepared_data キー: {list(prepared_data.keys())}")
                        else:
                            self.ai_response_display.append(f"[DEBUG] AITestWidget 課題IDが取得できませんでした")
                    except Exception as e:
                        self.ai_response_display.append(f"[ERROR] AITestWidget prepared_data生成エラー: {e}")
                        import traceback
                        self.ai_response_display.append(f"[ERROR] AITestWidget トレースバック: {traceback.format_exc()}")
                else:
                    self.ai_response_display.append(f"[DEBUG] AITestWidget AIコントローラー利用不可: ai_controller={ai_controller is not None}, parent={ai_controller.parent is not None if ai_controller else False}, data_methods={data_methods}")
            else:
                self.ai_response_display.append("[DEBUG] AITestWidget ARIM拡張チェックボックス無効のため、prepared_data生成スキップ")
            
            self.ai_response_display.append(f"[DEBUG] AITestWidget 最終prepared_data: {prepared_data}")
            
            full_prompt = self._build_analysis_prompt(prompt_template, experiment_data, static_data, prepared_data)
            
            # リクエスト内容を保存
            self._save_request_content(f"{method_name}プロンプト", full_prompt)
            
            # AI実行（一括/単体の分岐）
            if is_batch:
                return self._execute_batch_ai_analysis(method_name, full_prompt)
            else:
                return self._execute_single_ai_analysis(method_name, full_prompt)
                
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] {method_name}実行エラー: {e}")
            import traceback
            self.ai_response_display.append(f"[DEBUG] Traceback: {traceback.format_exc()}")

    def _execute_single_ai_analysis(self, method_name, full_prompt):
        """単体AI分析実行"""
        provider_id = self.ai_provider_combo.currentData()
        model = self.ai_model_combo.currentText()
        
        result = self.ai_manager.send_prompt(full_prompt, provider_id, model)
        
        # 結果処理
        if result["success"]:
            self.ai_response_display.append(f"[SUCCESS] {method_name}完了")
            if hasattr(self, 'ai_result_display'):
                self.ai_result_display.clear()
                self.ai_result_display.append(result.get("response", ""))
        else:
            self.ai_response_display.append(f"[ERROR] {method_name}に失敗: {result.get('error', '不明なエラー')}")
        
        return result

    def _execute_batch_ai_analysis(self, method_name, full_prompt):
        """バッチAI分析実行"""
        # バッチ処理のロジックは既存のコードから流用
        controller = self._get_ai_controller_with_setup()
        if not controller:
            return {"success": False, "error": "AIコントローラーの初期化に失敗"}
        
        # 一括分析実行
        return controller.execute_batch_analysis(full_prompt, method_name)

    def _build_analysis_prompt(self, prompt_template, experiment_data, static_data, prepared_data=None):
        """分析プロンプト構築（AIPromptManagerに委譲）"""
        try:
            # AIPromptManagerの使用を試行
            ai_controller = self._get_ai_controller_with_setup()
            if (ai_controller and hasattr(ai_controller.parent_controller, 'ai_prompt_manager') 
                and ai_controller.parent_controller.ai_prompt_manager):
                
                # 引数をマッピング（ui_ai_testの引数名 → AIPromptManagerの引数名）
                result = ai_controller.parent_controller.ai_prompt_manager.build_analysis_prompt(
                    template=prompt_template,
                    experiment_data=experiment_data, 
                    material_index=static_data,
                    prepared_data=prepared_data
                )
                return result
            
            # AIPromptManagerが利用できない場合のエラー
            self.ai_response_display.append("[ERROR] AIPromptManagerが利用できません。プロンプト構築に失敗しました。")
            return ""
            
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] プロンプト構築エラー: {e}")
            import traceback
            self.ai_response_display.append(f"[ERROR] スタックトレース: {traceback.format_exc()}")
            return ""
    
    def _prepare_data_common(self, method_name, fallback_method=None):
        """prepare_*系メソッドの共通処理（重複パターン統合）"""
        try:
            # 課題番号とデータを取得
            task_id = None
            experiment_data = {}
            
            # 単体実行の場合
            if hasattr(self, 'experiment_combo') and self.experiment_combo.currentIndex() >= 0:
                exp_data = self.experiment_combo.itemData(self.experiment_combo.currentIndex())
                if exp_data:
                    experiment_data.update(exp_data)
                    task_id = exp_data.get('課題番号', '不明')
            
            # 一括実行の場合  
            elif hasattr(self, 'task_id_combo') and self.task_id_combo.currentIndex() >= 0:
                task_id = self.task_id_combo.itemData(self.task_id_combo.currentIndex())
            
            # UI Controllerの対応メソッドに委譲
            if hasattr(self.parent_controller, method_name):
                parent_method = getattr(self.parent_controller, method_name)
                return parent_method(task_id, experiment_data)
            else:
                self.ai_response_display.append(f"[WARNING] 親コントローラーに{method_name}メソッドが見つかりません")
                return {}
                
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] {method_name}準備エラー: {e}")
            if fallback_method:
                return fallback_method()
            return {}
    
    # これ以降は元のUIControllerからコピーするメソッド群を配置予定
    # 今回はプレースホルダーとして関数名だけ定義します
    
    def _initialize_task_data(self):
        """タスクデータの初期化（遅延実行用、パフォーマンス最適化版）"""
        try:
            self._debug_print("[DEBUG] _initialize_task_data called")
            
            # ウィジェットの存在確認
            if not hasattr(self, 'task_id_combo'):
                if self._debug_enabled:
                    logger.error("task_id_combo is not initialized")
                return
                
            if not hasattr(self, 'experiment_combo'):
                if self._debug_enabled:
                    logger.error("experiment_combo is not initialized")
                return
                
            self._debug_print(f"[DEBUG] task_id_combo initialized: {self.task_id_combo is not None}")
            self._debug_print(f"[DEBUG] experiment_combo initialized: {self.experiment_combo is not None}")
            
            # データソース選択を初期化
            self._init_datasource_selection()
            
            # データソースの初期選択を確認
            try:
                if hasattr(self, 'arim_exp_radio') and hasattr(self, 'normal_exp_radio'):
                    if (self.arim_exp_radio is not None and self.arim_exp_radio.parent() is not None and
                        self.normal_exp_radio is not None and self.normal_exp_radio.parent() is not None):
                        self._debug_print(f"[DEBUG] arim_exp_radio checked: {self.arim_exp_radio.isChecked()}")
                        self._debug_print(f"[DEBUG] normal_exp_radio checked: {self.normal_exp_radio.isChecked()}")
                        
                        # どちらも選択されていない場合は、標準実験データを選択
                        if not self.arim_exp_radio.isChecked() and not self.normal_exp_radio.isChecked():
                            self._debug_print("[DEBUG] No datasource selected, defaulting to normal_exp_radio")
                            self.normal_exp_radio.setChecked(True)
                    else:
                        logger.debug("データソースラジオボタンが初期化されていません")
                else:
                    logger.debug("データソースラジオボタンが初期化されていません")
            except RuntimeError as radio_error:
                logger.debug("データソースラジオボタン操作時エラー: %s", radio_error)
            
            # 課題番号リストを更新
            self.refresh_task_ids()
            
        except Exception as e:
            logger.error("_initialize_task_data failed: %s", e)
            if self._debug_enabled:
                import traceback
                traceback.print_exc()
    
    def _init_ai_settings(self):
        """AI設定の初期化（パフォーマンス最適化版）"""
        try:
            self._debug_print("[DEBUG] _init_ai_settings 開始")
            
            # コンボボックスの存在確認
            if not hasattr(self, 'ai_provider_combo') or not hasattr(self, 'ai_model_combo'):
                if self._debug_enabled:
                    logger.error("AIコンボボックスが初期化されていません")
                # 遅延再実行
                QTimer.singleShot(200, self._init_ai_settings)
                return
                
            self._debug_print(f"[DEBUG] ai_provider_combo: {self.ai_provider_combo}")
            self._debug_print(f"[DEBUG] ai_model_combo: {self.ai_model_combo}")
            
            from classes.ai.core.ai_manager import AIManager
            self.ai_manager = AIManager()
            
            # AI Managerが正常に動作するかをテスト
            try:
                available_providers = self.ai_manager.get_available_providers()
                logger.debug("AI Manager正常動作確認: プロバイダー数=%s, プロバイダー=%s", len(available_providers), available_providers)
            except Exception as am_error:
                logger.error("AI Manager動作エラー: %s", am_error)
                return
            
            # 親コントローラーにAIManagerを設定（重要）
            self.parent_controller.ai_manager = self.ai_manager
            
            # デバッグ情報（出力量を削減）
            if self._debug_enabled:
                logger.debug("AI設定読み込み完了")
                logger.debug("デフォルトプロバイダー: %s", self.ai_manager.get_default_provider())
                logger.debug("利用可能プロバイダー: %s", self.ai_manager.get_available_providers())
            
            # プロバイダー一覧を更新
            logger.debug("プロバイダー一覧更新を開始")
            try:
                # ウィジェットが有効かチェック
                if hasattr(self, 'ai_provider_combo') and self.ai_provider_combo is not None:
                    logger.debug("ai_provider_combo存在確認: True, オブジェクト=%s", self.ai_provider_combo)
                    # 安全な操作を実行
                    safe_widget_operation(self.ai_provider_combo, self.ai_provider_combo.clear)
                    # ウィジェットが利用可能かより柔軟にチェック
                    try:
                        # 簡単な操作でウィジェットの有効性をテスト
                        current_count = self.ai_provider_combo.count()
                        logger.debug("ai_provider_combo current count: %s", current_count)
                        
                        providers = self.ai_manager.get_available_providers()
                        logger.debug("取得したプロバイダー一覧: %s", providers)
                        
                        for provider_id in providers:
                            display_name = provider_id.capitalize()  # プロバイダー名を表示用にフォーマット
                            self.ai_provider_combo.addItem(display_name, provider_id)
                            self._debug_print(f"[DEBUG] プロバイダー追加: {display_name} ({provider_id})")
                            
                        # 設定なしオプションを追加
                        self.ai_provider_combo.addItem("設定なし", None)
                        
                        # プロバイダー変更イベントを接続
                        try:
                            self.ai_provider_combo.currentTextChanged.disconnect()  # 既存接続をクリア
                        except:
                            pass  # 接続がない場合は無視
                        self.ai_provider_combo.currentTextChanged.connect(self._on_provider_changed)
                        logger.debug("ai_provider_combo設定完了: %s個のプロバイダー", self.ai_provider_combo.count())
                        
                    except RuntimeError as widget_error:
                        logger.debug("ai_provider_comboは無効です: %s", widget_error)
                        self.ai_provider_combo = None
                else:
                    logger.debug("ai_provider_comboが存在しません: hasattr=%s, is_not_none=%s", hasattr(self, 'ai_provider_combo'), getattr(self, 'ai_provider_combo', None) is not None)
            except RuntimeError as e:
                logger.debug("ai_provider_combo操作時エラー（削除済み）: %s", e)
                self.ai_provider_combo = None
            
            # デフォルトプロバイダーを設定
            if self.ai_provider_combo.count() > 1:
                default_provider = self.ai_manager.get_default_provider()
                self._debug_print(f"[DEBUG] デフォルトプロバイダー検索: {default_provider}")
                # デフォルトプロバイダーがリストにあるかチェック
                default_index = -1
                for i in range(self.ai_provider_combo.count()):
                    item_data = self.ai_provider_combo.itemData(i)
                    if self._debug_enabled:
                        logger.debug("コンボボックス項目 %s: %s (data: %s)", i, self.ai_provider_combo.itemText(i), item_data)
                    if item_data == default_provider:
                        default_index = i
                        break
                
                if default_index >= 0:
                    self._debug_print(f"[DEBUG] デフォルトプロバイダー見つかりました。インデックス: {default_index}")
                    self.ai_provider_combo.setCurrentIndex(default_index)
                else:
                    self._debug_print(f"[DEBUG] デフォルトプロバイダーが見つかりません。最初の項目を選択します。")
                    # デフォルトプロバイダーが見つからない場合は最初の有効なプロバイダーを選択
                    self.ai_provider_combo.setCurrentIndex(0)
            else:
                self.ai_provider_combo.setCurrentIndex(self.ai_provider_combo.count() - 1)
            
            # 選択されたプロバイダーに対応するモデルリストを初期化
            current_index = self.ai_provider_combo.currentIndex()
            if current_index >= 0:
                current_provider = self.ai_provider_combo.itemData(current_index)
                self._update_model_list(current_provider)
                
        except Exception as e:
            logger.error("AI設定初期化エラー: %s", e)
            # エラーハンドリング：設定なしのみ追加
            try:
                if hasattr(self, 'ai_provider_combo') and self.ai_provider_combo is not None:
                    try:
                        self.ai_provider_combo.clear()
                        self.ai_provider_combo.addItem("設定なし", None)
                        logger.debug("エラー処理でai_provider_comboに設定なしを追加")
                    except RuntimeError as widget_error:
                        logger.debug("ai_provider_combo（エラー処理）操作時エラー: %s", widget_error)
                        self.ai_provider_combo = None
            except Exception as clear_error:
                logger.debug("ai_provider_comboエラー処理失敗: %s", clear_error)
                self.ai_provider_combo = None
    
    def _update_model_list(self, provider):
        """選択されたプロバイダーのモデル一覧を更新"""
        try:
            # ウィジェットが有効かチェック
            if hasattr(self, 'ai_model_combo') and self.ai_model_combo is not None:
                try:
                    # 簡単な操作でウィジェットの有効性をテスト
                    current_count = self.ai_model_combo.count()
                    logger.debug("ai_model_combo current count: %s", current_count)
                    
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
                    logger.debug("ai_model_combo更新完了: %s個のモデル", self.ai_model_combo.count())
                    
                except RuntimeError as widget_error:
                    logger.debug("ai_model_comboは無効です: %s", widget_error)
                    self.ai_model_combo = None
            else:
                logger.debug("ai_model_comboが存在しません")
        except Exception as e:
            if hasattr(self, 'ai_response_display'):
                self.ai_response_display.append(f"モデル一覧の更新に失敗: {e}")
            else:
                logger.debug("モデル一覧の更新に失敗: %s", e)
    
    def _on_provider_changed(self, provider_name):
        """プロバイダー変更時のイベントハンドラー（パフォーマンス最適化版）"""
        try:
            # 現在選択されているプロバイダーのデータ（ID）を取得
            current_index = self.ai_provider_combo.currentIndex()
            if current_index >= 0:
                provider_id = self.ai_provider_combo.itemData(current_index)
                self._debug_print(f"[DEBUG] プロバイダー変更: {provider_name} (ID: {provider_id})")
                self._update_model_list(provider_id)
            else:
                self._debug_print(f"[DEBUG] プロバイダー変更: 無効なインデックス")
        except Exception as e:
            logger.error("プロバイダー変更エラー: %s", e)
    
    def _init_datasource_selection(self):
        """データソース選択の初期化（パフォーマンス最適化版）"""
        try:
            import os
            from config.common import get_dynamic_file_path
            
            # ラジオボタンの初期化を確認
            if not hasattr(self, 'arim_exp_radio') or not hasattr(self, 'normal_exp_radio'):
                self._debug_print("[DEBUG] データソースラジオボタンが初期化されていません - 遅延再実行")
                # QTimerを使用して遅延実行
                QTimer.singleShot(200, self._init_datasource_selection)
                return
            
            # datasource_info_labelの存在確認
            if not hasattr(self, 'datasource_info_label'):
                self._debug_print("[DEBUG] datasource_info_label が初期化されていません")
                return
            
            # ファイルの存在確認
            arim_exp_exists = os.path.exists(get_dynamic_file_path("input/ai/arim_exp.xlsx"))
            normal_exp_exists = os.path.exists(get_dynamic_file_path("input/ai/exp.xlsx"))
            
            if arim_exp_exists and normal_exp_exists:
                # 両方存在する場合はarim_exp.xlsxをデフォルトに
                try:
                    self.arim_exp_radio.setEnabled(True)
                    self.normal_exp_radio.setEnabled(True)
                    self.arim_exp_radio.setChecked(True)
                    self.datasource_info_label.setText("📊 両方のデータファイルが利用可能です。ARIM実験データがデフォルトで選択されています。")
                    self._debug_print("[DEBUG] 両方のファイルが存在 - ARIM実験データを選択")
                except RuntimeError as e:
                    logger.debug("RadioButton/Label操作エラー（両方存在）: %s", e)
            elif arim_exp_exists:
                # arim_exp.xlsxのみ存在
                try:
                    self.arim_exp_radio.setEnabled(True)
                    self.normal_exp_radio.setEnabled(False)
                    self.arim_exp_radio.setChecked(True)
                    self.datasource_info_label.setText("📊 ARIM実験データのみ利用可能です。")
                    self._debug_print("[DEBUG] ARIM実験データのみ存在")
                except RuntimeError as e:
                    logger.debug("RadioButton/Label操作エラー（ARIM存在）: %s", e)
            elif normal_exp_exists:
                # exp.xlsxのみ存在
                try:
                    self.arim_exp_radio.setEnabled(False)
                    self.normal_exp_radio.setEnabled(True)
                    self.normal_exp_radio.setChecked(True)
                    self.datasource_info_label.setText("📊 標準実験データのみ利用可能です。")
                    self._debug_print("[DEBUG] 標準実験データのみ存在")
                except RuntimeError as e:
                    logger.debug("RadioButton/Label操作エラー（標準存在）: %s", e)
            else:
                # どちらも存在しない
                try:
                    self.arim_exp_radio.setEnabled(False)
                    self.normal_exp_radio.setEnabled(False)
                    self.datasource_info_label.setText("⚠️ 実験データファイルが見つかりません。")
                    self._debug_print("[DEBUG] 実験データファイルが存在しません")
                except RuntimeError as e:
                    logger.debug("RadioButton/Label操作エラー（なし）: %s", e)
                
        except Exception as e:
            logger.error("データソース初期化エラー: %s", e)
            # ウィジェットが有効かチェックしてからアクセス
            try:
                if hasattr(self, 'datasource_info_label') and self.datasource_info_label is not None:
                    if self.datasource_info_label.parent() is not None:
                        self.datasource_info_label.setText(f"⚠️ データソース初期化エラー: {e}")
                    else:
                        logger.debug("datasource_info_labelは既に削除済みです")
            except RuntimeError as label_error:
                logger.debug("datasource_info_label操作時エラー: %s", label_error)
                self.datasource_info_label = None
    
    def refresh_task_ids(self):
        """課題番号リストを更新（パフォーマンス最適化版）"""
        try:
            # ai_response_displayが利用可能かチェック
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append("[INFO] 課題番号リストを更新中...")
            
            # 実験データの読み込み（キャッシュ機構使用）
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
            
            # コンボボックスの更新（デバッグ出力を削減）
            self._debug_print(f"[DEBUG] hasattr(self, 'task_id_combo'): {hasattr(self, 'task_id_combo')}")
            
            if hasattr(self, 'task_id_combo') and self.task_id_combo is not None:
                self.task_id_combo.clear()
                self._debug_print(f"[DEBUG] コンボボックスをクリア後の項目数: {self.task_id_combo.count()}")
                task_items = []
                
                if task_summary:
                    # 課題番号順にソート
                    sorted_tasks = sorted(task_summary.items())
                    
                    for task_id, info in sorted_tasks:
                        # 表示形式: "課題番号 (件数) - 課題名"
                        display_text = f"{task_id} ({info['count']}件) - {info['sample_title']}"
                        task_items.append(display_text)
                        self.task_id_combo.addItem(display_text, task_id)  # データとして実際の課題番号を保存
                    
                    self._debug_print(f"[DEBUG] コンボボックス項目数: {self.task_id_combo.count()}")
                    
                    # UIの強制更新
                    self.task_id_combo.update()
                    self.task_id_combo.repaint()
                    
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
                    selected_index = -1
                    for i in range(self.task_id_combo.count()):
                        if self.task_id_combo.itemData(i) == default_task:
                            self.task_id_combo.setCurrentIndex(i)
                            selected_index = i
                            break
                    else:
                        # デフォルト値が見つからない場合は最初の項目を選択
                        if self.task_id_combo.count() > 0:
                            self.task_id_combo.setCurrentIndex(0)
                            selected_index = 0
                    
                    # 選択された課題の詳細情報を明示的に更新
                    if selected_index >= 0:
                        selected_task_id = self.task_id_combo.itemData(selected_index)
                        if selected_task_id:
                            self._debug_print(f"[DEBUG] 初期選択課題の詳細情報を更新: {selected_task_id}")
                            self._update_task_info_display(selected_task_id)
                    
                    success_msg = f"[SUCCESS] 課題番号リストを更新: {len(task_summary)} 件"
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(success_msg)
                else:
                    self.task_id_combo.addItem("課題番号が見つかりません", "")
                    warning_msg = "[WARNING] 有効な課題番号が見つかりませんでした"
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(warning_msg)
                    else:
                        print(warning_msg)
            else:
                # コンボボックスが存在しない場合は、データのみ確認
                self._debug_print("[DEBUG] コンボボックスが存在しないため、UIは更新されません")
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
    
    def _load_experiment_data_for_task_list(self):
        """課題番号リスト用の実験データを読み込み（キャッシュ対応版）"""
        try:
            import pandas as pd
            import os
            from config.common import get_dynamic_file_path
            
            self._debug_print(f"[DEBUG] _load_experiment_data_for_task_list called")
            
            # データソース選択を確認
            use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                           self.arim_exp_radio.isChecked() and 
                           self.arim_exp_radio.isEnabled())
            
            data_source_key = "arim" if use_arim_data else "normal"
            self._debug_print(f"[DEBUG] use_arim_data: {use_arim_data}, cache_key: {data_source_key}")
            
            # キャッシュチェック（データソースが変更されていないかも確認）
            if (self._last_data_source == data_source_key and 
                data_source_key in self._data_source_cache):
                self._debug_print(f"[DEBUG] キャッシュからデータを取得: {data_source_key}")
                return self._data_source_cache[data_source_key]
            
            if use_arim_data:
                exp_file_path = get_dynamic_file_path("input/ai/arim_exp.xlsx")
                data_source_name = "ARIM実験データ"
            else:
                exp_file_path = get_dynamic_file_path("input/ai/exp.xlsx")
                data_source_name = "標準実験データ"
            
            self._debug_print(f"[DEBUG] 課題リスト用{data_source_name}を読み込み中: {exp_file_path}")
            
            # ファイル存在チェック
            if not os.path.exists(exp_file_path):
                error_msg = f"[ERROR] {data_source_name}ファイルが見つかりません: {exp_file_path}"
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(error_msg)
                else:
                    print(error_msg)
                return None
            
            # ファイルサイズチェック
            file_size = os.path.getsize(exp_file_path)
            self._debug_print(f"[DEBUG] ファイルサイズ: {file_size} bytes")
            if file_size == 0:
                error_msg = f"[ERROR] {data_source_name}ファイルが空です: {exp_file_path}"
                print(error_msg)
                return None
            
            # Excelファイルの読み込み
            try:
                self._debug_print(f"[DEBUG] pandas読み込み開始: {exp_file_path}")
                df = pd.read_excel(exp_file_path)
                self._debug_print(f"[DEBUG] pandas読み込み成功: {df.shape}")
            except pd.errors.EmptyDataError:
                error_msg = f"[ERROR] {data_source_name}ファイルにデータがありません: {exp_file_path}"
                print(error_msg)
                return None
            except Exception as read_error:
                error_msg = f"[ERROR] {data_source_name}ファイルの読み込みに失敗: {read_error}"
                print(error_msg)
                return None
            
            # データ内容チェック
            if df.empty:
                error_msg = f"[ERROR] {data_source_name}ファイルは空のデータフレームです"
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(error_msg)
                else:
                    print(error_msg)
                return None
            
            # 課題番号列の存在確認（データソースによって異なる）
            if use_arim_data:
                # ARIM実験データの場合は'ARIM ID'列を課題番号として使用
                if "ARIM ID" not in df.columns:
                    error_msg = "[ERROR] ARIM実験データに'ARIM ID'列が見つかりません"
                    info_msg = f"利用可能な列: {list(df.columns)}"
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(error_msg)
                        self.ai_response_display.append(info_msg)
                    else:
                        print(error_msg)
                        print(info_msg)
                    return None
                # ARIM IDを課題番号列としてマッピング
                df['課題番号'] = df['ARIM ID']
            else:
                # 標準実験データの場合は'課題番号'列を使用
                if "課題番号" not in df.columns:
                    error_msg = "[ERROR] 標準実験データに'課題番号'列が見つかりません"
                    info_msg = f"利用可能な列: {list(df.columns)}"
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(error_msg)
                        self.ai_response_display.append(info_msg)
                    else:
                        print(error_msg)
                        print(info_msg)
                    return None
            
            # DataFrameをJSON形式に変換
            experiments = df.to_dict('records')
            
            # キャッシュに保存
            self._data_source_cache[data_source_key] = experiments
            self._last_data_source = data_source_key
            self._debug_print(f"[DEBUG] データをキャッシュに保存: {data_source_key}, {len(experiments)} records")
            
            return experiments
            
        except ImportError:
            error_msg = "[ERROR] pandasライブラリがインストールされていません"
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(error_msg)
            else:
                print(error_msg)
            return None
        except Exception as e:
            error_msg = f"[ERROR] 実験データ読み込み処理中にエラーが発生: {e}"
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(error_msg)
            else:
                print(error_msg)
            return None
            try:
                logger.debug("pandas読み込み開始: %s", exp_file_path)
                df = pd.read_excel(exp_file_path)
                logger.debug("pandas読み込み成功: %s", df.shape)
            except pd.errors.EmptyDataError:
                error_msg = f"[ERROR] {data_source_name}ファイルにデータがありません: {exp_file_path}"
                print(error_msg)
                return None
            except Exception as read_error:
                error_msg = f"[ERROR] {data_source_name}ファイルの読み込みに失敗: {read_error}"
                print(error_msg)
                import traceback
                traceback.print_exc()
                return None
            
            # データ内容チェック
            if df.empty:
                error_msg = f"[ERROR] {data_source_name}ファイルは空のデータフレームです"
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(error_msg)
                else:
                    print(error_msg)
                return None
            
            # 課題番号列の存在確認（データソースによって異なる）
            if use_arim_data:
                # ARIM実験データの場合は'ARIM ID'列を課題番号として使用
                if "ARIM ID" not in df.columns:
                    error_msg = "[ERROR] ARIM実験データに'ARIM ID'列が見つかりません"
                    info_msg = f"利用可能な列: {list(df.columns)}"
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(error_msg)
                        self.ai_response_display.append(info_msg)
                    else:
                        print(error_msg)
                        print(info_msg)
                    return None
                # ARIM IDを課題番号列としてマッピング
                df['課題番号'] = df['ARIM ID']
            else:
                # 標準実験データの場合は'課題番号'列を使用
                if "課題番号" not in df.columns:
                    error_msg = "[ERROR] 標準実験データに'課題番号'列が見つかりません"
                    info_msg = f"利用可能な列: {list(df.columns)}"
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(error_msg)
                        self.ai_response_display.append(info_msg)
                    else:
                        print(error_msg)
                        print(info_msg)
                    return None
            
            # DataFrameをJSON形式に変換
            experiments = df.to_dict('records')
            
            return experiments
            
        except ImportError:
            error_msg = "[ERROR] pandasライブラリがインストールされていません"
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(error_msg)
            else:
                print(error_msg)
            return None
        except Exception as e:
            error_msg = f"[ERROR] 実験データ読み込み処理中にエラーが発生: {e}"
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(error_msg)
            else:
                print(error_msg)
            return None
    
    def on_task_index_changed(self, index):
        """課題インデックス変更時のイベント"""
        if index >= 0 and hasattr(self, 'task_id_combo'):
            task_id = self.task_id_combo.itemData(index)
            if task_id:
                logger.debug("on_task_index_changed: task_id=%s", task_id)
                self._update_task_info_display(task_id)
            else:
                # itemDataから取得できない場合は、テキストから抽出
                text = self.task_id_combo.currentText()
                import re
                match = re.match(r'^([A-Z0-9]+)', text.strip())
                if match:
                    task_id = match.group(1)
                    logger.debug("on_task_index_changed: extracted task_id=%s", task_id)
                    self._update_task_info_display(task_id)

    def on_completer_activated(self, text):
        """コンプリーター選択時のイベント"""
        self.task_id_combo.setCurrentText(text)
        # テキストから課題番号を抽出
        import re
        match = re.match(r'^([A-Z0-9]+)', text.strip())
        if match:
            task_id = match.group(1)
            logger.debug("on_completer_activated: task_id=%s", task_id)
            self._update_task_info_display(task_id)

    def show_experiment_info_popup(self):
        """実験データの詳細情報をポップアップ表示（親コントローラに委譲）"""
        return self.parent_controller.show_experiment_info_popup()
    
    def show_arim_extension_popup(self):
        """ARIM拡張情報をポップアップ表示（親コントローラに委譲）"""
        return self.parent_controller.show_arim_extension_popup()
    
    def _load_arim_extension_data(self):
        """ARIM拡張情報（converted.xlsx）を読み込む - UI Controller AIに委譲"""
        result = self.parent_controller.ai_controller._load_arim_extension_data()
        # current_arim_dataの設定を維持
        self.current_arim_data = result
        return result
    
    def _get_arim_data_for_task(self, task_id):
        """指定された課題番号に対応するARIM拡張データを取得"""
        try:
            logger.debug("_get_arim_data_for_task called for task_id: %s", task_id)
            
            if not task_id:
                logger.debug("task_id is empty")
                return []
                
            # ARIM拡張データを読み込み（キャッシュがあればそれを使用）
            arim_data = None
            if hasattr(self, 'current_arim_data') and self.current_arim_data:
                arim_data = self.current_arim_data
                logger.debug("Using cached ARIM data: %s records", len(arim_data))
            else:
                arim_data = self._load_arim_extension_data()
                logger.debug("Loaded fresh ARIM data: %s records", len(arim_data) if arim_data else 0)
            
            if not arim_data:
                logger.debug("No ARIM data available")
                return []
            
            matching_records = []
            
            # デバッグ: 最初の数件のレコード構造を確認
            logger.debug("Sample ARIM record columns: %s", list(arim_data[0].keys()) if arim_data else [])
            
            # 1. 課題番号での完全一致検索（最優先）
            for record in arim_data:
                kadai_no = record.get('課題番号', '')
                if kadai_no and str(kadai_no) == str(task_id):
                    matching_records.append(record)
                    logger.debug("Found exact task number match: %s", kadai_no)
            
            # 2. ARIMNO列での完全一致検索
            if not matching_records:
                for record in arim_data:
                    arimno = record.get('ARIMNO', '')
                    if arimno and str(arimno) == str(task_id):
                        matching_records.append(record)
                        logger.debug("Found exact ARIMNO match: %s", arimno)
            
            # 3. 課題番号での部分一致検索（末尾4桁一致など）
            if not matching_records and len(task_id) >= 4:
                task_suffix = task_id[-4:]  # 末尾4桁を取得
                logger.debug("Trying suffix search with: %s", task_suffix)
                
                for record in arim_data:
                    # 課題番号列での部分一致チェック
                    kadai_no = record.get('課題番号', '')
                    if kadai_no:
                        kadai_str = str(kadai_no)
                        # 末尾一致
                        if kadai_str.endswith(task_suffix):
                            matching_records.append(record)
                            logger.debug("Found task number suffix match: %s (suffix: %s)", kadai_no, task_suffix)
                        # 部分一致（含む）
                        elif task_suffix in kadai_str:
                            matching_records.append(record)
                            logger.debug("Found task number partial match: %s (contains: %s)", kadai_no, task_suffix)
                    
                    # ARIMNO列での部分一致チェック
                    arimno = record.get('ARIMNO', '')
                    if arimno:
                        arimno_str = str(arimno)
                        if arimno_str.endswith(task_suffix) and record not in matching_records:
                            matching_records.append(record)
                            logger.debug("Found ARIMNO suffix match: %s (suffix: %s)", arimno, task_suffix)
                        elif task_suffix in arimno_str and record not in matching_records:
                            matching_records.append(record)
                            logger.debug("Found ARIMNO partial match: %s (contains: %s)", arimno, task_suffix)
            
            # 4. より緩い検索：課題番号の一部分での検索
            if not matching_records:
                logger.debug("No matches found with standard methods, trying looser search...")
                
                # 課題番号から数字部分を抽出して検索
                import re
                task_numbers = re.findall(r'\d+', task_id)
                if task_numbers:
                    for num in task_numbers:
                        if len(num) >= 4:  # 4桁以上の数字のみ
                            logger.debug("Searching for number pattern: %s", num)
                            for record in arim_data:
                                kadai_no = record.get('課題番号', '')
                                arimno = record.get('ARIMNO', '')
                                
                                if kadai_no and num in str(kadai_no):
                                    if record not in matching_records:
                                        matching_records.append(record)
                                        logger.debug("Found number pattern match in task number: %s (pattern: %s)", kadai_no, num)
                                
                                if arimno and num in str(arimno):
                                    if record not in matching_records:
                                        matching_records.append(record)
                                        logger.debug("Found number pattern match in ARIMNO: %s (pattern: %s)", arimno, num)
            
            logger.debug("Found %s matching ARIM records for task_id: %s", len(matching_records), task_id)
            
            # マッチした記録の詳細をログ出力
            for i, record in enumerate(matching_records[:3]):  # 最初の3件のみ
                kadai = record.get('課題番号', 'N/A')
                arimno = record.get('ARIMNO', 'N/A')
                logger.debug("Match %s: 課題番号=%s, ARIMNO=%s", i+1, repr(kadai), repr(arimno))
            
            return matching_records
            
        except Exception as e:
            logger.error("_get_arim_data_for_task failed: %s", e)
            import traceback
            logger.error("Traceback: %s", traceback.format_exc())
            return []
    
    def show_task_info_popup(self):
        """課題詳細情報をポップアップ表示（親コントローラに委譲）"""
        return self.parent_controller.show_task_info_popup()
    
    def show_request_popup(self):
        """リクエスト内容をポップアップ表示（親コントローラに委譲）"""
        return self.parent_controller.show_request_popup()

    def show_response_popup(self):
        """AIレスポンス内容をポップアップ表示（親コントローラに委譲）"""
        return self.parent_controller.show_response_popup()
    
    def on_analysis_method_changed(self, index):
        """分析方法が変更された時の処理"""
        try:
            if index >= 0 and hasattr(self, 'analysis_method_combo') and hasattr(self, 'analysis_description_label'):
                method_data = self.analysis_method_combo.itemData(index)
                if method_data:
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
                    
                    # 単体処理の場合は実験データ選択が必要であることを強調
                    if exec_type == "SINGLE":
                        self.analysis_description_label.setText(f"{extended_description}\n⚠️ 単体の実験データを選択してください")
                    
                    # デバッグ情報出力
                    logger.debug("分析方法変更: %s", self.analysis_method_combo.itemText(index))
                    logger.debug("説明更新: %s", description)
                        
        except Exception as e:
            logger.error("分析方法変更処理エラー: %s", e)
            if hasattr(self, 'analysis_description_label'):
                self.analysis_description_label.setText(f"エラー: {e}")
    
    def execute_ai_analysis(self):
        """選択された分析方法に基づいてAI分析を実行（直接AIコントローラーを使用）"""
        try:
            # 共通ヘルパーでAIコントローラーを取得・設定
            ai_controller = self._get_ai_controller_with_setup()
            if not ai_controller:
                return
            
            # メインのAI分析実行（強制ログ機能付き）
            return ai_controller.execute_ai_analysis()
                
        except Exception as e:
            try:
                self.ai_response_display.append(f"[ERROR] AI分析実行中にエラーが発生: {e}")
                import traceback
                self.ai_response_display.append(f"[DEBUG] Traceback: {traceback.format_exc()}")
            except RuntimeError:
                # UIコンポーネントが削除されている場合はコンソールに出力
                logger.error("AI分析実行中にエラーが発生: %s", e)
                import traceback
                logger.debug("Traceback: %s", traceback.format_exc())
    
    def on_task_id_changed(self, text):
        """課題番号が変更された時の処理（簡略版）これは使われてる。"""
        try:
            logger.debug("on_task_id_changed called with text: '%s'", text)
            
            # 重複呼び出し防止のためのフラグチェック
            if hasattr(self, '_updating_task_info') and self._updating_task_info:
                logger.debug("Already updating task info, skipping duplicate call")
                return
                
            # 必要なコンポーネントの安全な存在確認
            if not hasattr(self, 'task_id_combo') or not self.task_id_combo:
                logger.debug("task_id_combo does not exist")
                return
                
            self._updating_task_info = True
            
            try:
                # 現在選択されている課題番号の詳細情報を取得
                current_index = self.task_id_combo.currentIndex()
                logger.debug("current_index: %s", current_index)
                
                task_id = None
                if current_index >= 0:
                    task_id = self.task_id_combo.itemData(current_index)
                    logger.debug("task_id from itemData: '%s'", task_id)
                
                # itemDataから取得できない場合は、テキストから課題番号を抽出
                if not task_id and text:
                    # 表示形式: "課題番号 (件数) - 課題名" から課題番号部分を抽出
                    import re
                    match = re.match(r'^([A-Z0-9]+)', text.strip())
                    if match:
                        task_id = match.group(1)
                        logger.debug("task_id extracted from text: '%s'", task_id)
                
                if task_id and hasattr(self, 'task_info_label'):
                    # 課題詳細情報を表示
                    self._update_task_info_display(task_id)
                    
                    # 実験データリストを更新
                    self._update_experiment_list(task_id)
                else:
                    logger.debug("task_id is empty or task_info_label not found")
                    if hasattr(self, 'task_info_label'):
                        self.task_info_label.setText("課題番号を選択してください")
                    
                    # TODO: その他の更新処理
                        
            finally:
                self._updating_task_info = False
                
        except Exception as e:
            logger.error("on_task_id_changed failed: %s", e)
            # エラー時もフラグをリセット
            if hasattr(self, '_updating_task_info'):
                self._updating_task_info = False
    
    def _update_task_info_display(self, task_id):
        """課題情報表示を更新"""
        try:
            logger.debug("Updating task info for: %s", task_id)
            
            exp_data = self._load_experiment_data_for_task_list()
            logger.debug("exp_data loaded: %s records", len(exp_data) if exp_data else 0)
            
            if exp_data:
                matching_experiments = [exp for exp in exp_data if exp.get("課題番号") == task_id]
                logger.debug("matching_experiments for '%s': %s records", task_id, len(matching_experiments))
                
                if matching_experiments:
                    sample_exp = matching_experiments[0]
                    info_lines = []
                    info_lines.append(f"📋 課題番号: {task_id}")
                    info_lines.append(f"📊 実験データ件数: {len(matching_experiments)}件")
                    
                    # データソースに応じて表示する項目を変更
                    use_arim_data = (hasattr(self, 'arim_exp_radio') and 
                                   self.arim_exp_radio.isChecked() and 
                                   self.arim_exp_radio.isEnabled())
                    
                    if use_arim_data:
                        # ARIM実験データの場合
                        if sample_exp.get("タイトル"):
                            info_lines.append(f"📝 タイトル: {sample_exp['タイトル']}")
                        
                        if sample_exp.get("概要"):
                            summary_val = sample_exp["概要"]
                            if summary_val and not self._is_nan_value(summary_val):
                                summary = str(summary_val).strip()
                                if summary:
                                    if len(summary) > 80:
                                        summary = summary[:80] + "..."
                                    info_lines.append(f"🎯 概要: {summary}")
                        
                        if sample_exp.get("分野"):
                            info_lines.append(f"🔬 分野: {sample_exp['分野']}")
                        
                        device_val = sample_exp.get("利用装置")
                        if device_val and not self._is_nan_value(device_val):
                            device = str(device_val).strip()
                            if device:
                                if len(device) > 50:
                                    device = device[:50] + "..."
                                info_lines.append(f"� 利用装置: {device}")
                    else:
                        # 標準実験データの場合
                        if sample_exp.get("課題名"):
                            info_lines.append(f"📝 課題名: {sample_exp['課題名']}")
                        
                        if sample_exp.get("目的"):
                            purpose_val = sample_exp["目的"]
                            if purpose_val and not self._is_nan_value(purpose_val):
                                purpose = str(purpose_val).strip()
                                if purpose:
                                    if len(purpose) > 80:
                                        purpose = purpose[:80] + "..."
                                    info_lines.append(f"🎯 目的: {purpose}")
                        
                        facility_val = sample_exp.get("施設・設備")
                        if facility_val and not self._is_nan_value(facility_val):
                            facility = str(facility_val).strip()
                            if facility:
                                info_lines.append(f"🏢 施設・設備: {facility}")
                    
                    # 課題情報の表示を更新
                    info_text = "\n".join(info_lines)
                    if hasattr(self, 'task_info_label') and self.task_info_label:
                        self.task_info_label.setText(info_text)
                        logger.debug("Task info updated: %s", info_text)
                        
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
                self.task_info_label.setText("課題を選択してください")
        except Exception as e:
            logger.error("_clear_task_info_display failed: %s", e)

    def _is_nan_value(self, value):
        """pandas NaN値かどうかを判定"""
        try:
            import pandas as pd
            return pd.isna(value)
        except:
            return value is None or str(value).lower() in ['nan', 'none', '']
    
    def _update_experiment_list(self, task_id):
        """実験データリストを更新"""
        try:
            logger.debug("_update_experiment_list called for task: %s", task_id)
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
    
    def _load_experiment_data_for_task(self, task_id):
        """特定の課題ID用の実験データを読み込み"""
        try:
            # 全実験データを読み込み
            all_exp_data = self._load_experiment_data_for_task_list()
            if all_exp_data is None:
                return None
            
            import pandas as pd
            
            # DataFrameに変換
            df = pd.DataFrame(all_exp_data)
            
            # 指定されたtask_idでフィルタリング
            filtered_data = df[df['課題番号'] == task_id]
            
            return filtered_data
            
        except Exception as e:
            error_msg = f"[ERROR] 課題別実験データ読み込み中にエラーが発生: {e}"
            print(error_msg)
            return None
    
    def on_datasource_changed(self, button):
        """データソースが変更された時の処理"""
        logger.debug("Datasource changed to: %s", button.text())
        
        try:
            # データソース情報を更新
            if hasattr(self, 'datasource_info_label'):
                if button.text() == "ARIM実験データ":
                    self.datasource_info_label.setText("📊 ARIM実験データソースを使用中")
                elif button.text() == "標準実験データ":
                    self.datasource_info_label.setText("📊 標準実験データソースを使用中")
                else:
                    self.datasource_info_label.setText(f"📊 データソース: {button.text()}")
            
            # 課題番号リストを再読み込み
            if hasattr(self, 'refresh_task_ids'):
                self.refresh_task_ids()
                logger.debug("Task IDs refreshed after datasource change")
                
        except Exception as e:
            logger.error("データソース変更処理エラー: %s", e)
            if hasattr(self, 'datasource_info_label'):
                self.datasource_info_label.setText(f"❌ データソース変更エラー: {e}")
    
    def on_experiment_changed(self, index):
        """実験データが変更された時の処理"""
        try:
            logger.debug("Experiment changed to index: %s", index)
            
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
    
    def on_ai_provider_changed(self, provider_text):
        """AIプロバイダーが変更された時の処理"""
        try:
            logger.debug("AI provider changed to: %s", provider_text)
            
            # コンボボックスからプロバイダーIDを取得
            current_index = self.ai_provider_combo.currentIndex()
            if current_index >= 0:
                provider_id = self.ai_provider_combo.itemData(current_index)
                logger.debug("Provider ID: %s", provider_id)
                
                # モデル一覧を更新
                self._update_model_list(provider_id)
                
                # AI設定情報をログ表示
                if hasattr(self, 'ai_response_display'):
                    self.ai_response_display.append(f"[INFO] AIプロバイダーを {provider_text} に変更しました")
            
        except Exception as e:
            logger.error("AIプロバイダー変更処理エラー: %s", e)
            if hasattr(self, 'ai_response_display'):
                self.ai_response_display.append(f"[ERROR] プロバイダー変更エラー: {e}")
    
    def test_ai_connection(self):
        """AI接続テスト（UIControllerAIに委譲）"""
        try:
            # UIControllerAIの対応メソッドに委譲
            ai_controller = self._get_ai_controller_with_setup()
            if ai_controller:
                return ai_controller.test_ai_connection()
            else:
                if hasattr(self, 'ai_response_display'):
                    self.ai_response_display.append("[ERROR] AIコントローラーが利用できません")
        except Exception as e:
            if hasattr(self, 'ai_response_display'):
                self.ai_response_display.append(f"[ERROR] AI接続テスト委譲エラー: {e}")
    
    def send_ai_prompt(self):
        """AIにプロンプトを送信（UIControllerAIに委譲）"""
        try:
            # UIControllerAIの対応メソッドに委譲
            ai_controller = self._get_ai_controller_with_setup()
            if ai_controller:
                return ai_controller.send_ai_prompt()
            else:
                if hasattr(self, 'ai_response_display'):
                    self.ai_response_display.append("[ERROR] AIコントローラーが利用できません")
        except Exception as e:
            if hasattr(self, 'ai_response_display'):
                self.ai_response_display.append(f"[ERROR] AIプロンプト送信委譲エラー: {e}")
    
    def show_progress(self, message="処理中...", current=0, total=100):
        """プログレス表示を開始（親コントローラに委譲）"""
        return self.parent_controller.show_progress(message, current, total)
    
    def update_progress(self, current, total, message=None):
        """プログレス更新（親コントローラに委譲）"""
        return self.parent_controller.update_progress(current, total, message)
    
    def hide_progress(self):
        """プログレス非表示（親コントローラに委譲）"""
        return self.parent_controller.hide_progress()
    
    def show_text_area_expanded(self, text_widget, title):
        """テキストエリアの内容を拡大表示（親コントローラに委譲）"""
        return self.parent_controller.show_text_area_expanded(text_widget, title)
    
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
                if self.parent_controller._is_valid_data_value(experiment.get("タイトル")):
                    info_lines.append(f"📝 タイトル: {str(experiment['タイトル']).strip()}")
                else:
                    info_lines.append("📝 タイトル: 未設定")
                
                if self.parent_controller._is_valid_data_value(experiment.get("実験日")):
                    info_lines.append(f"📅 実験日: {str(experiment['実験日']).strip()}")
                else:
                    info_lines.append("📅 実験日: 未設定")
                
                if self.parent_controller._is_valid_data_value(experiment.get("実験装置")):
                    info_lines.append(f"🔧 実験装置: {str(experiment['実験装置']).strip()}")
                elif self.parent_controller._is_valid_data_value(experiment.get("利用装置")):
                    info_lines.append(f"🔧 利用装置: {str(experiment['利用装置']).strip()}")
                else:
                    info_lines.append("🔧 実験装置: 未設定")
                
                info_lines.append("─" * 30)
                
                if self.parent_controller._is_valid_data_value(experiment.get("ARIM ID")):
                    info_lines.append(f"🔢 ARIM ID: {str(experiment['ARIM ID']).strip()}")
                
                if self.parent_controller._is_valid_data_value(experiment.get("課題番号")):
                    info_lines.append(f"📋 課題番号: {str(experiment['課題番号']).strip()}")
                
                if self.parent_controller._is_valid_data_value(experiment.get("年度")):
                    info_lines.append(f"📅 年度: {str(experiment['年度']).strip()}")
                
                if self.parent_controller._is_valid_data_value(experiment.get("課題クラス")):
                    info_lines.append(f"📊 課題クラス: {str(experiment['課題クラス']).strip()}")
                
                if self.parent_controller._is_valid_data_value(experiment.get("申請者番号")):
                    info_lines.append(f"👤 申請者番号: {str(experiment['申請者番号']).strip()}")
                
                if self.parent_controller._is_valid_data_value(experiment.get("所属機関区分")):
                    info_lines.append(f"🏢 所属機関区分: {str(experiment['所属機関区分']).strip()}")
            else:
                # 標準実験データの場合 - 主要情報を最初に表示
                if self.parent_controller._is_valid_data_value(experiment.get("課題名")):
                    info_lines.append(f"📝 課題名: {str(experiment['課題名']).strip()}")
                else:
                    info_lines.append("📝 課題名: 未設定")
                
                if self.parent_controller._is_valid_data_value(experiment.get("実験実施日")):
                    info_lines.append(f"📅 実験実施日: {str(experiment['実験実施日']).strip()}")
                else:
                    info_lines.append("📅 実験実施日: 未設定")
                
                if self.parent_controller._is_valid_data_value(experiment.get("測定装置")):
                    info_lines.append(f"🔧 測定装置: {str(experiment['測定装置']).strip()}")
                else:
                    info_lines.append("🔧 測定装置: 未設定")
                
                info_lines.append("─" * 30)
                
                if self.parent_controller._is_valid_data_value(experiment.get("実験ID")):
                    info_lines.append(f"🔢 実験ID: {str(experiment['実験ID']).strip()}")
                
                if self.parent_controller._is_valid_data_value(experiment.get("施設・設備")):
                    info_lines.append(f"🏢 施設・設備: {str(experiment['施設・設備']).strip()}")
                
                if self.parent_controller._is_valid_data_value(experiment.get("試料名")):
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
                if self.parent_controller._is_valid_data_value(experiment.get(col)):
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

    def _validate_task_and_experiment_selection(self, exec_type="SINGLE"):
        """課題番号と実験データの選択状態を検証（UIControllerAIに委譲）"""
        try:
            # UIControllerAIの対応メソッドに委譲
            ai_controller = self._get_ai_controller_with_setup()
            if ai_controller:
                return ai_controller._validate_task_and_experiment_selection(exec_type)
            else:
                return {"valid": False, "message": "AIコントローラーが利用できません"}
        except Exception as e:
            return {"valid": False, "message": f"選択状態検証委譲エラー: {e}"}

    def _execute_analysis_single(self, method_name, prompt_file, data_methods, static_files):
        """単体分析の実行（AIコントローラーに委譲）"""
        try:
            # 共通ヘルパーでAIコントローラーを取得・設定
            ai_controller = self._get_ai_controller_with_setup()
            if not ai_controller:
                return
            
            # メインのAI分析実行（強制ログ機能付き）
            return ai_controller._execute_analysis_single(method_name, prompt_file, data_methods, static_files)
                
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] 単体分析エラー: {e}")
            import traceback
            self.ai_response_display.append(f"[DEBUG] Traceback: {traceback.format_exc()}")

    def _execute_analysis_batch(self, method_name, prompt_file, data_methods, static_files):
        """一括分析の実行（AIコントローラーに委譲）"""
        try:
            # 共通ヘルパーでAIコントローラーを取得・設定
            ai_controller = self._get_ai_controller_with_setup()
            if not ai_controller:
                return
            
            # メインのAI分析実行（強制ログ機能付き）
            return ai_controller._execute_analysis_batch(method_name, prompt_file, data_methods, static_files)
                
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] 一括分析エラー: {e}")
            import traceback
            self.ai_response_display.append(f"[DEBUG] Traceback: {traceback.format_exc()}")

    def analyze_material_index_single(self, data_methods=None, static_files=None):
        """マテリアルインデックス分析を実行（AIコントローラーに委譲）"""
        try:
            # 共通ヘルパーでAIコントローラーを取得・設定
            ai_controller = self._get_ai_controller_with_setup()
            if not ai_controller:
                return
            
            # 特別な設定
            ai_controller.parent.ai_provider_combo = self.ai_provider_combo if hasattr(self, 'ai_provider_combo') else None
            ai_controller.parent.ai_model_combo = self.ai_model_combo if hasattr(self, 'ai_model_combo') else None
            
            # AITestWidget独自の_execute_analysisメソッドを使用してARIM拡張情報処理を行う
            self.ai_response_display.append("[DEBUG] AITestWidget execute_material_index_analysis: _execute_analysis呼び出し開始")
            return self._execute_analysis("MI分析（単体）", "material_index.txt", data_methods or [], static_files or [], is_batch=False)
                
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] マテリアルインデックス分析エラー: {e}")
            import traceback
            self.ai_response_display.append(f"[DEBUG] Traceback: {traceback.format_exc()}")

    def _execute_material_index_batch(self, method_name, data_methods, static_files):
        """マテリアルインデックス分析（一括）を実行（AIコントローラーに委譲）"""
        try:
            # 共通ヘルパーでAIコントローラーを取得・設定
            ai_controller = self._get_ai_controller_with_setup()
            if not ai_controller:
                return
            
            # 特別な設定
            ai_controller.parent.ai_provider_combo = self.ai_provider_combo if hasattr(self, 'ai_provider_combo') else None
            ai_controller.parent.ai_model_combo = self.ai_model_combo if hasattr(self, 'ai_model_combo') else None
            
            # メインのAI分析実行（material_index.txt使用、一括モード）
            return ai_controller._execute_analysis_batch(method_name, "material_index.txt", data_methods or [], static_files or [])
                
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] マテリアルインデックス一括分析エラー: {e}")
            import traceback
            self.ai_response_display.append(f"[DEBUG] Traceback: {traceback.format_exc()}")

    # ヘルパーメソッド群
    
    def _get_ai_provider_and_model(self):
        """AIプロバイダーとモデルを取得"""
        try:
            if not hasattr(self, 'ai_provider_combo') or not hasattr(self, 'ai_model_combo'):
                return None, None
            
            provider_index = self.ai_provider_combo.currentIndex()
            if provider_index < 0:
                return None, None
            
            provider_id = self.ai_provider_combo.itemData(provider_index)
            if not provider_id:
                return None, None
            
            model_index = self.ai_model_combo.currentIndex()
            if model_index < 0:
                return None, None
            
            model = self.ai_model_combo.itemData(model_index)
            if not model:
                model = self.ai_model_combo.currentText()
            
            return provider_id, model
            
        except Exception as e:
            return None, None
    
    def _get_selected_experiment_data(self):
        """選択された実験データを取得"""
        try:
            if not hasattr(self, 'experiment_combo') or self.experiment_combo.currentIndex() < 0:
                return None
            
            experiment_data = self.experiment_combo.itemData(self.experiment_combo.currentIndex())
            return experiment_data
            
        except Exception as e:
            logger.error("実験データ取得エラー: %s", e)
            return None
    
    def _enhance_with_arim_data(self, experiment_data):
        """ARIM拡張データとの結合"""
        try:
            if not experiment_data:
                return experiment_data
            
            # ARIM拡張チェックボックスの状態確認
            if not (hasattr(self, 'arim_extension_checkbox') and self.arim_extension_checkbox.isChecked()):
                return experiment_data
            
            # 課題番号を取得
            task_id = experiment_data.get('課題番号', '')
            if not task_id:
                return experiment_data
            
            # ARIM拡張データを取得
            arim_data = self._get_arim_data_for_task(task_id)
            if arim_data:
                # 拡張データとマージ
                enhanced_data = experiment_data.copy()
                enhanced_data['arim_extension'] = arim_data
                return enhanced_data
            
            return experiment_data
            
        except Exception as e:
            logger.error("ARIM拡張データ結合エラー: %s", e)
            return experiment_data
    
    def _load_static_file_data(self, static_files):
        """静的データファイルを読み込み（キャッシュ対応版）"""
        try:
            if not static_files:
                return {}
            
            static_data = {}
            for file_name in static_files:
                # キャッシュチェック
                if file_name in self._cached_static_data:
                    self._debug_print(f"[DEBUG] キャッシュから静的ファイル取得: {file_name}")
                    static_data[file_name] = self._cached_static_data[file_name]
                    continue
                
                try:
                    from config.common import get_static_resource_path,get_dynamic_file_path
                    file_path = get_dynamic_file_path(f'input/ai/{file_name}')

                    if os.path.exists(file_path):
                        if file_name.endswith('.json'):
                            import json
                            with open(file_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                static_data[file_name] = data
                                self._cached_static_data[file_name] = data  # キャッシュに保存
                        elif file_name.endswith('.xlsx'):
                            df = pd.read_excel(file_path)
                            data = df.to_dict('records')
                            static_data[file_name] = data
                            self._cached_static_data[file_name] = data  # キャッシュに保存
                        else:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                data = f.read()
                                static_data[file_name] = data
                                self._cached_static_data[file_name] = data  # キャッシュに保存
                    else:
                        if hasattr(self, 'ai_response_display') and self.ai_response_display:
                            self.ai_response_display.append(f"[WARNING] 静的ファイルが見つかりません: {file_name}")
                        
                except Exception as e:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[ERROR] 静的ファイル {file_name} 読み込みエラー: {e}")
            
            return static_data
            
        except Exception as e:
            logger.error("静的データ読み込みエラー: %s", e)
            return {}
    
    def _build_dataset_explanation_prompt(self, experiment_data, static_data):
        """データセット説明用のプロンプトを構築"""
        prompt = f"""データセットの詳細説明を生成してください。

実験データ:
{json.dumps(experiment_data, ensure_ascii=False, indent=2)}

以下の観点から詳細な説明を提供してください：
1. データセットの概要と目的
2. 実験条件と手法
3. 取得されたデータの種類と特徴
4. データの品質と信頼性
5. 分析における注意点や制限事項

200文字程度で簡潔にまとめてください。"""
        
        return prompt
    
    def _build_experiment_method_prompt(self, experiment_data, static_data):
        """実験手法分析用のプロンプトを構築"""
        prompt = f"""実験手法と装置の詳細分析を実行してください。

実験データ:
{json.dumps(experiment_data, ensure_ascii=False, indent=2)}

静的データ:
{json.dumps(static_data, ensure_ascii=False, indent=2)}

以下の観点から分析してください：
1. 使用された実験手法の特徴
2. 装置・機器の仕様と性能
3. 実験条件の妥当性
4. 手法の長所と制限事項
5. 改善提案

200文字程度で簡潔にまとめてください。"""
        
        return prompt
    
    def _build_quality_assessment_prompt(self, experiment_data, static_data):
        """品質評価用のプロンプトを構築（一括）"""
        prompt = f"""実験データの品質評価を実行してください。

実験データ:
{json.dumps(experiment_data, ensure_ascii=False, indent=2)}

以下の観点から評価してください：
1. データの完整性
2. 実験手法の適切性
3. 結果の再現性
4. 統計的有意性
5. 総合品質スコア（1-10）

200文字程度で簡潔にまとめてください。"""
        
        return prompt
    
    def _build_generic_prompt(self, template, experiment_data, static_data):
        """汎用的なプロンプトを構築"""
        try:
            # テンプレート内の変数を置換
            prompt = template
            
            # 実験データの挿入
            exp_data_str = json.dumps(experiment_data, ensure_ascii=False, indent=2)
            prompt = prompt.replace("{experiment_data}", exp_data_str)
            
            # 静的データの挿入
            static_data_str = json.dumps(static_data, ensure_ascii=False, indent=2)
            prompt = prompt.replace("{static_data}", static_data_str)
            
            return prompt
            
        except Exception as e:
            logger.error("プロンプト構築エラー: %s", e)
            return template
    
    def _build_material_index_prompt(self, experiment_data, material_index, static_data):
        """マテリアルインデックス分析用のプロンプトを構築"""
        try:
            # material_index.txtテンプレートを読み込み
            template = self._load_prompt_template("material_index.txt")
            if not template:
                # フォールバックプロンプト
                prompt = f"""以下の実験データとマテリアルインデックスを用いて分析を行ってください。

実験データ:
{json.dumps(experiment_data, ensure_ascii=False, indent=2)}

マテリアルインデックス:
{json.dumps(material_index, ensure_ascii=False, indent=2)}

材料特性と実験結果の関係を分析し、マテリアルインデックスとの相関を調べてください。
結果を200文字程度で簡潔にまとめてください。"""
                return prompt
            
            # テンプレート内の変数を置換
            prompt = template
            
            # 実験データの挿入
            exp_data_str = json.dumps(experiment_data, ensure_ascii=False, indent=2)
            prompt = prompt.replace("{experiment_data}", exp_data_str)
            
            # マテリアルインデックスの挿入
            mi_data_str = json.dumps(material_index, ensure_ascii=False, indent=2)
            prompt = prompt.replace("{material_index}", mi_data_str)
            
            # 静的データの挿入
            if static_data:
                static_data_str = json.dumps(static_data, ensure_ascii=False, indent=2)
                prompt = prompt.replace("{static_data}", static_data_str)
            
            return prompt
            
        except Exception as e:
            logger.error("MI分析プロンプト構築エラー: %s", e)
            # エラー時のフォールバックプロンプト
            return f"""実験データとマテリアルインデックスの分析を実行してください。

実験データ: {str(experiment_data)[:500]}...
マテリアルインデックス: {str(material_index)[:300]}...

分析結果を200文字程度で簡潔にまとめてください。"""

    def _execute_ai_request(self, prompt, provider_id, model, analysis_name):
        """AI分析リクエストを実行"""
        try:
            # リクエスト内容を保存
            self.last_request_content = prompt
            self.last_request_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # AI分析実行
            result = self.ai_manager.send_prompt(prompt, provider_id, model)
            
            if result["success"]:
                self.ai_response_display.append(f"[SUCCESS] {analysis_name}完了")
                
                # モデル名と応答時間を表示
                if "model" in result:
                    self.ai_response_display.append(f"使用モデル: {result['model']}")
                if "response_time" in result:
                    self.ai_response_display.append(f"応答時間: {result['response_time']:.2f}秒")
                
                # レスポンス情報を保存
                self.last_response_info = {
                    "model": result.get("model", "不明"),
                    "response_time": result.get("response_time", 0),
                    "usage": result.get("usage", {}),
                    "success": True,
                    "analysis_type": analysis_name
                }
                
                # 分析結果を結果表示欄に表示
                response_content = result.get("response", "")
                if response_content and hasattr(self, 'ai_result_display'):
                    self.ai_result_display.clear()
                    self.ai_result_display.append(response_content)
                
            else:
                self.ai_response_display.append(f"[ERROR] {analysis_name}に失敗: {result.get('error', '不明なエラー')}")
                
                # エラー時の情報を保存
                self.last_response_info = {
                    "model": result.get("model", "不明"),
                    "response_time": result.get("response_time", 0),
                    "usage": result.get("usage", {}),
                    "success": False,
                    "error": result.get("error", "不明なエラー"),
                    "analysis_type": analysis_name
                }
            
            return result
            
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] AI分析実行エラー: {e}")
            return {"success": False, "error": str(e)}

    def _hide_progress(self):
        """プログレス表示を非表示（hide_progressのエイリアス）"""
        self.hide_progress()

    def _load_material_index(self):
        """マテリアルインデックスデータを読み込み"""
        try:
            from config.common import get_static_resource_path, get_dynamic_file_path
            import os
            import json
            
            # MI.jsonファイルのパス
            mi_file_path = get_dynamic_file_path('input/ai/MI.json')
            
            if not os.path.exists(mi_file_path):
                self.ai_response_display.append(f"[WARNING] マテリアルインデックスファイルが見つかりません: {mi_file_path}")
                return {}
            
            # JSONファイルを読み込み
            with open(mi_file_path, 'r', encoding='utf-8') as f:
                mi_data = json.load(f)
            
            self.ai_response_display.append(f"[INFO] マテリアルインデックスを読み込みました: {len(mi_data)} 項目")
            return mi_data
            
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] マテリアルインデックス読み込みエラー: {e}")
            return {}

    def _load_prompt_template(self, template_file):
        """プロンプトテンプレートを読み込み（キャッシュ対応版・ファイル更新時刻チェック付き）"""
        try:
            from config.common import get_static_resource_path,get_dynamic_file_path
            import os
            
            # プロンプトテンプレートファイルのパス
            template_path = get_dynamic_file_path(f'input/ai/prompts/{template_file}')
            
            # ファイルの最終更新時刻を確認
            file_exists = os.path.exists(template_path)
            current_mtime = None
            if file_exists:
                current_mtime = os.path.getmtime(template_path)
            
            # キャッシュチェック（ファイル更新時刻も考慮）
            cached_mtime = self._template_file_times.get(template_file)
            if (template_file in self._cached_templates and 
                cached_mtime is not None and 
                current_mtime is not None and 
                cached_mtime == current_mtime):
                self._debug_print(f"[DEBUG] キャッシュからテンプレート取得: {template_file}")
                return self._cached_templates[template_file]
            
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(f"[DEBUG] テンプレートファイル探索: {template_path}")
            
            if not file_exists:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[WARNING] プロンプトテンプレートが見つかりません: {template_path}")
                    self.ai_response_display.append(f"[INFO] デフォルトテンプレートを使用します")
                template = self._get_default_prompt_template(template_file)
                # デフォルトテンプレートもキャッシュに保存（更新時刻はNone）
                self._cached_templates[template_file] = template
                self._template_file_times[template_file] = None
                return template
            
            # テンプレートファイルを読み込み
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # キャッシュに保存（更新時刻も記録）
            self._cached_templates[template_file] = template
            self._template_file_times[template_file] = current_mtime
            
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(f"[INFO] プロンプトテンプレートを読み込みました: {template_file} ({len(template)}文字)")
                if current_mtime != cached_mtime:
                    self.ai_response_display.append(f"[INFO] ファイル更新を検出: {template_file}")
            
            return template
            
        except Exception as e:
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(f"[ERROR] プロンプトテンプレート読み込みエラー: {e}")
            template = self._get_default_prompt_template(template_file)
            # エラー時のデフォルトテンプレートもキャッシュに保存
            self._cached_templates[template_file] = template
            self._template_file_times[template_file] = None
            return template

    def _get_default_prompt_template(self, template_file):
        """デフォルトプロンプトテンプレートを取得"""
        if template_file == "material_index.txt":
            return """以下の実験データとマテリアルインデックスを基に、マテリアル分析を実行してください。

実験データ:
{experiment_data}

マテリアルインデックス:
{material_index}

分析観点:
1. 実験データの特徴
2. マテリアル特性の評価
3. インデックスとの関連性
4. 今後の研究方向性

200文字程度で簡潔にまとめてください。"""
        
        elif template_file == "dataset_explanation.txt":
            return """以下の実験データセットについて、詳細な説明を生成してください。

実験データ:
{experiment_data}

静的データ:
{static_data}

説明内容:
1. データセットの概要
2. 実験手法と条件
3. 測定項目と特徴
4. データの品質と信頼性
5. 活用可能性と応用分野

データセットの特徴を分かりやすく説明してください。"""
        
        elif template_file == "experiment_method.txt":
            return """以下の実験データを基に、実験手法と装置について詳細に分析してください。

実験データ:
{experiment_data}

装置情報:
{static_data}

分析項目:
1. 使用された実験装置の特徴
2. 測定手法と実験条件
3. データ取得プロセス
4. 実験設計の妥当性
5. 手法の利点と限界

実験手法の技術的側面を詳しく解説してください。"""
        
        elif template_file == "quality_assessment.txt":
            return """以下の実験データについて、品質評価を実行してください。

実験データ:
{experiment_data}

品質基準:
{static_data}

評価項目:
1. データの完整性（欠損値、異常値）
2. 測定精度と再現性
3. 実験条件の一貫性
4. データの信頼性評価
5. 改善提案

データ品質を総合的に評価し、具体的な改善点を提示してください。"""
        
        else:
            return """実験データの分析を実行してください。

実験データ:
{experiment_data}

静的データ:
{static_data}

分析内容:
1. データの特徴と傾向
2. 重要な発見事項
3. データの解釈
4. 今後の課題

200文字程度で簡潔にまとめてください。"""

    def open_prompt_template_editor(self):
        """プロンプトテンプレート編集ダイアログを開く"""
        try:
            # 現在選択されている分析方法を取得
            current_index = self.analysis_method_combo.currentIndex()
            if current_index < 0:
                # 適切な親ウィジェットを取得してMessageBoxを表示
                parent_widget = self._get_parent_widget()
                QMessageBox.warning(parent_widget, "警告", "分析方法が選択されていません。")
                return
            
            method_name = self.analysis_method_combo.currentText()
            method_data = self.analysis_method_combo.itemData(current_index)
            
            if not method_data:
                parent_widget = self._get_parent_widget()
                QMessageBox.warning(parent_widget, "警告", "選択された分析方法のデータが見つかりません。")
                return
            
            prompt_file = method_data.get("prompt_file", "")
            if not prompt_file:
                parent_widget = self._get_parent_widget()
                QMessageBox.warning(parent_widget, "警告", "選択された分析方法にプロンプトファイルが設定されていません。")
                return
            
            # 現在のテンプレートを読み込み
            current_template = self._load_prompt_template(prompt_file)
            
            # デフォルトテンプレートを取得
            default_template = self._get_default_prompt_template(prompt_file)
            
            # 適切な親ウィジェットを取得
            parent_widget = self._get_parent_widget()
            
            # 編集ダイアログを表示
            dialog = PromptTemplateEditorDialog(
                parent_widget, method_name, prompt_file, current_template, default_template
            )
            
            if dialog.exec() == QDialog.Accepted:
                # 編集内容が保存された場合、応答メッセージを表示
                self.ai_response_display.append(f"[INFO] プロンプトテンプレート「{prompt_file}」が更新されました")
                self.ai_response_display.append(f"[INFO] 次回の分析実行時から新しいテンプレートが使用されます")
                
                # 重要：テンプレートキャッシュをクリアして新しい内容を反映
                self.clear_template_cache(prompt_file)
                
                # さらに確実に反映させるため、全キャッシュもクリア
                self.clear_template_cache()  # 全テンプレートキャッシュクリア
                
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] プロンプトテンプレート編集エラー: {e}")
            parent_widget = self._get_parent_widget()
            QMessageBox.critical(parent_widget, "エラー", f"プロンプトテンプレート編集中にエラーが発生しました。\n\n{e}")

    def _get_parent_widget(self):
        """適切な親ウィジェットを取得"""
        # parent_controllerから適切なウィジェットを取得
        if hasattr(self.parent_controller, 'widget') and self.parent_controller.widget:
            return self.parent_controller.widget
        elif hasattr(self.parent_controller, 'parent') and self.parent_controller.parent:
            return self.parent_controller.parent
        else:
            # フォールバック: Noneを返してシステムのデフォルト親を使用
            return None

    def _merge_with_arim_data(self, experiment_data, arim_data):
        """実験データとARIM拡張データを結合（UIControllerAIに委譲）"""
        try:
            # UIControllerAIの対応メソッドに委譲
            ai_controller = self._get_ai_controller_with_setup()
            if ai_controller:
                return ai_controller._merge_with_arim_data(experiment_data, arim_data)
            else:
                if hasattr(self, 'ai_response_display'):
                    self.ai_response_display.append("[ERROR] AIコントローラーが利用できません")
                return experiment_data
        except Exception as e:
            if hasattr(self, 'ai_response_display'):
                self.ai_response_display.append(f"[ERROR] ARIMデータ結合委譲エラー: {e}")
            return experiment_data

    # =================================================================
    # データ準備メソッド群

    def prepare_exp_info(self):
        """基本実験情報を準備（共通処理使用）"""
        return self._prepare_data_common("prepare_exp_info")

    def prepare_exp_info_ext(self):
        """拡張実験情報を準備（共通処理使用）"""
        return self._prepare_data_common("prepare_exp_info_ext", fallback_method=self.prepare_exp_info)

    def prepare_device_info(self):
        """装置・デバイス情報を準備（共通処理使用）"""
        return self._prepare_data_common("prepare_device_info")

    def prepare_quality_metrics(self):
        """品質評価指標を準備（共通処理使用）"""
        return self._prepare_data_common("prepare_quality_metrics")

    def prepare_materials_data(self):
        """材料データを準備"""
        try:
            materials_data = {}
            
            # 基本実験情報を取得
            exp_data = self.prepare_exp_info()
            
            # 材料関連の情報を抽出
            material_keywords = ["材料", "物質", "元素", "組成", "化学式", "分子", "原子"]
            for key, value in exp_data.items():
                if any(keyword in str(key) for keyword in material_keywords):
                    materials_data[key] = value
            
            # 材料特性を抽出
            property_keywords = ["密度", "硬度", "強度", "弾性", "熱", "電気", "磁気"]
            for key, value in exp_data.items():
                if any(keyword in str(key) for keyword in property_keywords):
                    materials_data[key] = value
            
            self.ai_response_display.append(f"[DEBUG] 材料データ準備完了: {len(materials_data)}件")
            return materials_data
            
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] 材料データ準備エラー: {e}")
            return {}

    def prepare_analysis_data(self):
        """分析データを準備"""
        try:
            analysis_data = {}
            
            # 基本実験情報を取得
            exp_data = self.prepare_exp_info()
            
            # 分析関連の情報を抽出
            analysis_keywords = ["分析", "測定", "評価", "検査", "試験", "結果", "データ"]
            for key, value in exp_data.items():
                if any(keyword in str(key) for keyword in analysis_keywords):
                    analysis_data[key] = value
            
            # 数値データの統計情報を追加
            numerical_data = {}
            for key, value in exp_data.items():
                try:
                    # 数値変換を試行
                    if isinstance(value, (int, float)):
                        numerical_data[key] = value
                    elif isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit():
                        numerical_data[key] = float(value)
                except:
                    continue
            
            if numerical_data:
                analysis_data["数値データ統計"] = {
                    "項目数": len(numerical_data),
                    "最大値": max(numerical_data.values()) if numerical_data else None,
                    "最小値": min(numerical_data.values()) if numerical_data else None
                }
            
            self.ai_response_display.append(f"[DEBUG] 分析データ準備完了: {len(analysis_data)}件")
            return analysis_data
            
        except Exception as e:
            self.ai_response_display.append(f"[ERROR] 分析データ準備エラー: {e}")
            return {}

    def _save_request_content(self, request_type, content):
        """リクエスト内容を履歴として保存"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 履歴エントリを作成
        history_entry = {
            "timestamp": timestamp,
            "type": request_type,
            "content": content,
            "char_count": len(content)
        }
        
        # 履歴に追加（最大100件まで保持）
        self.request_history.append(history_entry)
        if len(self.request_history) > 100:
            self.request_history.pop(0)
        
        # 最後のリクエスト内容を更新
        self.last_request_content = f"=== {request_type} ===\n{content}"
        self.last_request_time = timestamp
        
        # デバッグ: プロンプト内容の要約を表示
        content_preview = content[:200] + "..." if len(content) > 200 else content
        self.ai_response_display.append(f"[DEBUG] リクエスト内容保存: {request_type} ({len(content)}文字)")
        self.ai_response_display.append(f"[DEBUG] プロンプト開始部分: {content_preview}")
        
        # ARIM拡張データの有無をチェック
        has_arim_data = 'arim_extension' in content.lower()
        experiment_data_present = 'experiment_data' in content or '課題番号' in content
        mi_data_present = 'material_index' in content or 'マテリアル' in content
        
        self.ai_response_display.append(f"[DEBUG] 内容チェック - ARIM拡張: {has_arim_data}, 実験データ: {experiment_data_present}, MI: {mi_data_present}")

    def _get_full_request_history_text(self):
        """全リクエスト履歴をテキスト形式で取得"""
        if not self.request_history:
            return "リクエスト履歴はありません。"
        
        history_text = "=== 全リクエスト履歴 ===\n\n"
        
        for i, entry in enumerate(reversed(self.request_history), 1):
            history_text += f"【{i}】 {entry['type']} ({entry['timestamp']})\n"
            history_text += f"文字数: {entry['char_count']} 文字\n"
            history_text += "-" * 50 + "\n"
            history_text += entry['content']
            history_text += "\n" + "=" * 50 + "\n\n"
        
        return history_text

    def _execute_dataset_explanation_single(self, method_name, data_methods, static_files):
        """データセット説明分析の単体実行（共通処理使用）"""
        return self._execute_analysis_common(
            "データセット説明分析",
            "dataset_explanation.txt",
            data_methods,
            static_files,
            is_batch=False
        )

    def _execute_experiment_method_single(self, method_name, data_methods, static_files):
        """実験手法分析の単体実行（共通処理使用）"""
        return self._execute_analysis_common(
            "実験手法分析",
            "experiment_method.txt",
            data_methods,
            static_files,
            is_batch=False
        )

    def _execute_quality_assessment_batch(self, method_name, data_methods, static_files):
        """品質評価の一括実行（共通処理使用）"""
        return self._execute_analysis_common(
            "品質評価（一括）",
            "quality_assessment.txt",
            data_methods,
            static_files,
            is_batch=True
        )

    def _execute_generic_analysis_single(self, method_name, prompt_file, data_methods, static_files):
        """汎用単体分析の実行（共通処理使用）"""
        return self._execute_analysis_common(
            method_name,
            prompt_file,
            data_methods,
            static_files,
            is_batch=False
        )

    def _execute_generic_analysis_batch(self, method_name, prompt_file, data_methods, static_files):
        """汎用一括分析の実行（共通処理使用）"""
        return self._execute_analysis_common(
            method_name,
            prompt_file,
            data_methods,
            static_files,
            is_batch=True
        )
