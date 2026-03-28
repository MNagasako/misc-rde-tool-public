"""Dialog for managing AI extension button definitions."""

from __future__ import annotations

import copy
import json
import logging

from typing import Optional

from qt_compat.widgets import (
    QDialog,
    QAbstractItemView,
    QApplication,
    QComboBox,
    QCheckBox,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QSizePolicy,
)
from qt_compat.core import Qt, Signal, QThread, QTimer

from classes.ai.util.prompt_assembly import (
    apply_prompt_dictionary_candidates,
    build_prompt_dictionary_from_output,
    build_prompt_dictionary_merge_preview,
    detect_prompt_assembly_sources,
    evaluate_prompt_dictionary_benchmarks,
    get_prompt_assembly_source_catalog,
    get_prompt_dictionary_summary,
    load_prompt_dictionary_config,
    save_prompt_dictionary_config,
)
from classes.dataset.util.ai_extension_config_manager import AIExtensionConfigManager
from classes.dataset.util.ai_extension_helper import infer_ai_suggest_target_kind, load_prompt_file
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color


logger = logging.getLogger("RDE_AI")

_PROMPT_DICTIONARY_ALIAS_VIEW_LIMIT = 5000
_PROMPT_DICTIONARY_CANDIDATE_VIEW_LIMIT = 300
_PROMPT_DICTIONARY_TERM_VIEW_LIMIT = 300
_PROMPT_DICTIONARY_LIST_TEXT_LIMIT = 40
_PROMPT_DICTIONARY_JSON_PREVIEW_MAX_CHARS = 20000
_PROMPT_SOURCE_REFRESH_DELAY_MS = 120


class PromptSourcePreviewThread(QThread):
    preview_ready = Signal(object)
    error_occurred = Signal(str, int)

    def __init__(
        self,
        request_id: int,
        *,
        inline_template: str,
        prompt_file: str,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._inline_template = inline_template or ""
        self._prompt_file = prompt_file or ""

    def run(self) -> None:
        try:
            template_text = self._inline_template.strip()
            if not template_text and self._prompt_file.strip():
                template_text = load_prompt_file(self._prompt_file.strip()) or ""
            self.preview_ready.emit(
                {
                    "request_id": self._request_id,
                    "detected_sources": detect_prompt_assembly_sources(template_text),
                }
            )
        except Exception as exc:
            logger.warning("prompt source preview build failed", exc_info=True)
            self.error_occurred.emit(str(exc), self._request_id)


class PromptDictionaryLoadThread(QThread):
    loaded = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.result_config: dict = {}

    def run(self) -> None:
        try:
            self.result_config = load_prompt_dictionary_config()
            self.loaded.emit(get_prompt_dictionary_summary(self.result_config))
        except Exception as exc:
            logger.warning("prompt dictionary background load failed", exc_info=True)
            self.error_occurred.emit(str(exc))


class PromptDictionaryBuildThread(QThread):
    progress_changed = Signal(object)
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, config: dict, max_files_per_source: int = 2000, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._config = copy.deepcopy(config or {})
        self._max_files_per_source = max(1, int(max_files_per_source or 1))
        self.result_config: dict = {}

    def run(self) -> None:
        try:
            self.result_config = build_prompt_dictionary_from_output(
                self._config,
                max_files_per_source=self._max_files_per_source,
                progress_callback=lambda payload: self.progress_changed.emit(payload),
                persist=True,
            )
            self.result_ready.emit(get_prompt_dictionary_summary(self.result_config))
        except Exception as exc:
            logger.warning("prompt dictionary background build failed", exc_info=True)
            self.error_occurred.emit(str(exc))


class AIExtensionConfigDialog(QDialog):
    """UI to add/remove/reorder AI extension definition buttons."""

    config_saved = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("AIサジェスト機能定義の管理")
        # できるだけスクロールバーが不要になるよう、少し大きめに確保
        self.resize(1480, 780)
        self.setModal(True)

        self._manager = AIExtensionConfigManager()
        self._locked_ids = {btn.get('id') for btn in self._manager.buttons if not btn.get('allow_delete', False)}
        self._current_index: int = -1
        self._is_loading_form = False
        self._prompt_source_catalog = get_prompt_assembly_source_catalog()
        self._prompt_dictionary_config = {}
        self._prompt_dictionary_loaded = False
        self._dictionary_load_thread: Optional[PromptDictionaryLoadThread] = None
        self._dictionary_tab: Optional[QWidget] = None
        self._source_mode_widgets = {}
        self._dictionary_candidate_status_widgets = {}
        self._dictionary_build_thread: Optional[PromptDictionaryBuildThread] = None
        self._dictionary_progress_messages = []
        self._prompt_source_refresh_timer = QTimer(self)
        self._prompt_source_refresh_timer.setSingleShot(True)
        self._prompt_source_refresh_timer.timeout.connect(self._start_prompt_source_refresh)
        self._prompt_source_preview_thread: Optional[PromptSourcePreviewThread] = None
        self._prompt_source_request_seq = 0
        self._prompt_source_active_request_id = 0
        self._prompt_source_pending_request: Optional[dict] = None
        # 設定キーが未存在でも従来のデフォルトを維持
        self._dataset_desc_prompt_button_id = (
            self._manager.get_dataset_description_ai_proposal_prompt_button_id() or "json_explain_dataset_basic"
        )
        self._quick_ai_prompt_button_id = self._manager.get_dataset_quick_ai_prompt_button_id() or ""
        if not self._quick_ai_prompt_button_id:
            if self._manager.find_by_id("dataset_explanation_quick") is not None:
                self._quick_ai_prompt_button_id = "dataset_explanation_quick"

        self._ai_check_prompt_button_id = self._manager.get_dataset_ai_check_prompt_button_id() or ""
        if not self._ai_check_prompt_button_id:
            if self._manager.find_by_id("json_check_dataset_summary_simple_quality") is not None:
                self._ai_check_prompt_button_id = "json_check_dataset_summary_simple_quality"

        self._build_ui()
        self._apply_dialog_size_policy()
        self._refresh_button_list(select_index=0)

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        message_label = QLabel(
            "AIサジェストボタンの定義を追加・削除・並び替えできます。\n"
            "🔒 マークの付いたボタンはアプリの他機能で使用中のため削除できません。"
        )
        message_label.setWordWrap(True)
        message_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        message_label.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {get_color(ThemeKey.TEXT_SECONDARY)};"
        )
        layout.addWidget(message_label)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setMinimumHeight(0)
        splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(splitter, 1)

        # Left: button list + controls
        left_panel = QWidget()
        left_panel.setMinimumHeight(0)
        left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)

        self.button_list = QListWidget()
        self.button_list.setMinimumHeight(0)
        self.button_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.button_list.currentRowChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.button_list, 1)

        controls_layout = QHBoxLayout()
        self.add_button = QPushButton("追加")
        self.add_button.clicked.connect(self._on_add_button)
        self.delete_button = QPushButton("削除")
        self.delete_button.clicked.connect(self._on_delete_button)
        self.move_up_button = QPushButton("↑ 上へ")
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_down_button = QPushButton("↓ 下へ")
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))

        controls_layout.addWidget(self.add_button)
        controls_layout.addWidget(self.delete_button)
        controls_layout.addWidget(self.move_up_button)
        controls_layout.addWidget(self.move_down_button)
        left_layout.addLayout(controls_layout)

        splitter.addWidget(left_panel)

        # Right: detail editor
        right_panel = QWidget()
        right_panel.setMinimumHeight(0)
        right_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)

        self.editor_tabs = QTabWidget()
        self.editor_tabs.setMinimumHeight(0)
        self.editor_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout.addWidget(self.editor_tabs)

        editor_tab = QWidget()
        editor_tab_layout = QVBoxLayout(editor_tab)
        editor_tab_layout.setContentsMargins(0, 0, 0, 0)

        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        editor_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        editor_scroll.setMinimumHeight(0)
        editor_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        editor_content = QWidget()
        editor_layout = QVBoxLayout(editor_content)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.id_edit = QLineEdit()
        form.addRow("ID", self.id_edit)

        self.label_edit = QLineEdit()
        form.addRow("表示ラベル", self.label_edit)

        self.icon_edit = QLineEdit()
        self.icon_edit.setPlaceholderText("例: 🤖")
        form.addRow("アイコン", self.icon_edit)

        self.category_edit = QLineEdit()
        form.addRow("カテゴリ", self.category_edit)

        self.prompt_file_edit = QLineEdit()
        self.prompt_file_edit.textChanged.connect(self._schedule_prompt_source_refresh)
        form.addRow("プロンプトファイル", self.prompt_file_edit)

        self.target_kind_combo = QComboBox()
        self.target_kind_combo.addItem("データセット", "dataset")
        self.target_kind_combo.addItem("報告書", "report")
        form.addRow("対象", self.target_kind_combo)

        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(["text", "json"])
        form.addRow("出力形式", self.output_format_combo)

        self.prompt_assembly_mode_combo = QComboBox()
        self.prompt_assembly_mode_combo.addItem("全文埋め込み（full_embed）", "full_embed")
        self.prompt_assembly_mode_combo.addItem("候補限定埋め込み（filtered_embed）", "filtered_embed")
        self.prompt_assembly_mode_combo.setToolTip(
            "STATIC_MI_TREE などの巨大静的データを、全文のまま埋め込むか、候補限定して埋め込むかを指定します。"
        )
        form.addRow("プロンプト組み立て方式", self.prompt_assembly_mode_combo)

        self.dataset_desc_prompt_checkbox = QCheckBox("「データセット説明 AI提案」のプロンプトテンプレートとして使用")
        self.dataset_desc_prompt_checkbox.setToolTip(
            "AI説明文提案（AI提案タブ）で使用するプロンプトを、このボタンのプロンプトに切り替えます。\n"
            "選択できるのは1つだけで、最後にチェックしたものが優先されます。\n"
            "※ 出力形式が json のボタンのみ推奨です。"
        )
        self.dataset_desc_prompt_checkbox.toggled.connect(self._on_dataset_desc_prompt_toggled)
        form.addRow("データセット説明AI提案", self.dataset_desc_prompt_checkbox)

        self.quick_ai_prompt_checkbox = QCheckBox("「⚡ Quick AI」のプロンプトテンプレートとして使用")
        self.quick_ai_prompt_checkbox.setToolTip(
            "⚡ Quick AI で使用するプロンプトを、このボタンのプロンプトに切り替えます。\n"
            "選択できるのは1つだけで、最後にチェックしたものが優先されます。"
        )
        self.quick_ai_prompt_checkbox.toggled.connect(self._on_quick_ai_prompt_toggled)
        form.addRow("⚡ Quick AI", self.quick_ai_prompt_checkbox)

        self.ai_check_prompt_checkbox = QCheckBox("「📋 AI CHECK」のプロンプトテンプレートとして使用")
        self.ai_check_prompt_checkbox.setToolTip(
            "📋 AI CHECK で使用するプロンプトを、このボタンのプロンプトに切り替えます。\n"
            "選択できるのは1つだけで、最後にチェックしたものが優先されます。\n"
            "※ JSON出力のプロンプトが推奨です（スコア等の表示が安定します）。"
        )
        self.ai_check_prompt_checkbox.toggled.connect(self._on_ai_check_prompt_toggled)
        form.addRow("📋 AI CHECK", self.ai_check_prompt_checkbox)

        self.allow_delete_checkbox = QCheckBox("このボタンの削除を許可する")
        form.addRow("削除許可", self.allow_delete_checkbox)

        editor_layout.addLayout(form)

        desc_label = QLabel("説明")
        desc_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        editor_layout.addWidget(desc_label)
        self.description_edit = QTextEdit()
        self.description_edit.setFixedHeight(80)
        editor_layout.addWidget(self.description_edit)

        template_label = QLabel("インラインテンプレート (任意)")
        template_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        editor_layout.addWidget(template_label)
        self.prompt_template_edit = QTextEdit()
        self.prompt_template_edit.setPlaceholderText("ファイルではなくインラインでプロンプトを定義する場合に使用")
        self.prompt_template_edit.textChanged.connect(self._schedule_prompt_source_refresh)
        editor_layout.addWidget(self.prompt_template_edit, 1)

        source_label = QLabel("フィルター対象ごとの組み立て設定")
        source_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        editor_layout.addWidget(source_label)

        self.prompt_source_table = QTableWidget(0, 4)
        self.prompt_source_table.setHorizontalHeaderLabels(["対象", "方式", "フィルター方法", "実例"])
        self.prompt_source_table.verticalHeader().setVisible(False)
        self.prompt_source_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.prompt_source_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.prompt_source_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.prompt_source_table.setAlternatingRowColors(True)
        self.prompt_source_table.setMinimumHeight(0)
        self.prompt_source_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        header = self.prompt_source_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        editor_layout.addWidget(self.prompt_source_table)

        self.prompt_source_detail = QPlainTextEdit()
        self.prompt_source_detail.setReadOnly(True)
        self.prompt_source_detail.setPlaceholderText("上の行を選択すると、フィルター方法の説明と実例を詳しく表示します。")
        self.prompt_source_detail.setFixedHeight(120)
        editor_layout.addWidget(self.prompt_source_detail)
        self.prompt_source_table.itemSelectionChanged.connect(self._update_prompt_source_detail)

        editor_layout.addStretch(1)
        editor_scroll.setWidget(editor_content)
        editor_tab_layout.addWidget(editor_scroll, 1)

        self.editor_tabs.addTab(editor_tab, "ボタン定義")
        self._dictionary_tab = self._build_dictionary_tab()
        self.editor_tabs.addTab(self._dictionary_tab, "辞書管理")
        self.editor_tabs.currentChanged.connect(self._on_editor_tab_changed)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        # Footer buttons
        footer = QHBoxLayout()
        footer.addStretch()
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self._on_save)
        self.cancel_button = QPushButton("閉じる")
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.save_button)
        footer.addWidget(self.cancel_button)
        layout.addLayout(footer)

        self._apply_button_theme(self.add_button, ThemeKey.BUTTON_PRIMARY_BACKGROUND)
        self._apply_button_theme(self.delete_button, ThemeKey.BUTTON_DANGER_BACKGROUND)
        self._apply_button_theme(self.move_up_button, ThemeKey.BUTTON_NEUTRAL_BACKGROUND)
        self._apply_button_theme(self.move_down_button, ThemeKey.BUTTON_NEUTRAL_BACKGROUND)
        self._apply_button_theme(self.save_button, ThemeKey.BUTTON_SUCCESS_BACKGROUND)
        self._apply_button_theme(self.cancel_button, ThemeKey.BUTTON_NEUTRAL_BACKGROUND)
        self._refresh_prompt_dictionary_views()
        self._set_prompt_dictionary_build_running(False)

    def _build_dictionary_tab(self) -> QWidget:
        widget = QWidget()
        widget.setMinimumHeight(0)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(widget)

        toolbar = QHBoxLayout()
        self.dictionary_scan_button = QPushButton("output から辞書作成")
        self.dictionary_scan_button.clicked.connect(self._on_prompt_dictionary_scan)
        self.dictionary_apply_button = QPushButton("承認済みを適用")
        self.dictionary_apply_button.clicked.connect(self._on_prompt_dictionary_apply)
        self.dictionary_evaluate_button = QPushButton("評価実行")
        self.dictionary_evaluate_button.clicked.connect(self._on_prompt_dictionary_evaluate)
        self.dictionary_web_assist_checkbox = QCheckBox("WEB補助を有効化")
        self.dictionary_llm_assist_checkbox = QCheckBox("LLM補助を有効化")
        toolbar.addWidget(self.dictionary_scan_button)
        toolbar.addWidget(self.dictionary_apply_button)
        toolbar.addWidget(self.dictionary_evaluate_button)
        toolbar.addWidget(self.dictionary_web_assist_checkbox)
        toolbar.addWidget(self.dictionary_llm_assist_checkbox)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.dictionary_progress_label = QLabel("辞書作成は未実行です。")
        layout.addWidget(self.dictionary_progress_label)

        self.dictionary_progress_bar = QProgressBar()
        self.dictionary_progress_bar.setRange(0, 1)
        self.dictionary_progress_bar.setValue(0)
        self.dictionary_progress_bar.setVisible(True)
        layout.addWidget(self.dictionary_progress_bar)

        self.dictionary_progress_log = QPlainTextEdit()
        self.dictionary_progress_log.setReadOnly(True)
        self.dictionary_progress_log.setFixedHeight(120)
        self.dictionary_progress_log.setPlaceholderText("辞書作成中の途中経過を表示します。")
        layout.addWidget(self.dictionary_progress_log)

        self.dictionary_tabs = QTabWidget()
        self.dictionary_tabs.setMinimumHeight(0)
        self.dictionary_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.dictionary_tabs, 1)

        self.dictionary_summary_view = QPlainTextEdit()
        self.dictionary_summary_view.setReadOnly(True)
        self.dictionary_tabs.addTab(self.dictionary_summary_view, "概要")

        alias_tab = QWidget()
        alias_layout = QVBoxLayout(alias_tab)
        alias_layout.setContentsMargins(0, 0, 0, 0)

        alias_toolbar = QHBoxLayout()
        self.dictionary_add_alias_button = QPushButton("Alias追加")
        self.dictionary_add_alias_button.clicked.connect(self._on_add_dictionary_alias_row)
        self.dictionary_remove_alias_button = QPushButton("選択Alias削除")
        self.dictionary_remove_alias_button.clicked.connect(self._on_remove_dictionary_alias_row)
        alias_toolbar.addWidget(self.dictionary_add_alias_button)
        alias_toolbar.addWidget(self.dictionary_remove_alias_button)
        alias_toolbar.addStretch()
        alias_layout.addLayout(alias_toolbar)

        self.dictionary_alias_table = QTableWidget(0, 3)
        self.dictionary_alias_table.setMinimumHeight(0)
        self.dictionary_alias_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.dictionary_alias_table.setHorizontalHeaderLabels(["canonical", "aliases", "source"])
        self.dictionary_alias_table.verticalHeader().setVisible(False)
        self.dictionary_alias_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.dictionary_alias_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.dictionary_alias_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.SelectedClicked
        )
        self.dictionary_alias_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.dictionary_alias_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.dictionary_alias_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        alias_layout.addWidget(self.dictionary_alias_table, 1)
        self.dictionary_tabs.addTab(alias_tab, "Alias 一覧")

        self.dictionary_stopword_table = QTableWidget(0, 3)
        self.dictionary_stopword_table.setMinimumHeight(0)
        self.dictionary_stopword_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.dictionary_stopword_table.setHorizontalHeaderLabels(["kind", "tokens", "source"])
        self.dictionary_stopword_table.verticalHeader().setVisible(False)
        self.dictionary_stopword_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dictionary_stopword_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.dictionary_stopword_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.dictionary_stopword_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.dictionary_tabs.addTab(self.dictionary_stopword_table, "Stopword 一覧")

        self.dictionary_source_override_table = QTableWidget(0, 5)
        self.dictionary_source_override_table.setMinimumHeight(0)
        self.dictionary_source_override_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.dictionary_source_override_table.setHorizontalHeaderLabels(["source", "alias数", "stopword数", "weak数", "allowlist数"])
        self.dictionary_source_override_table.verticalHeader().setVisible(False)
        self.dictionary_source_override_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dictionary_source_override_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.dictionary_source_override_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.dictionary_source_override_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.dictionary_source_override_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.dictionary_source_override_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.dictionary_tabs.addTab(self.dictionary_source_override_table, "Source Overrides")

        self.dictionary_candidate_table = QTableWidget(0, 7)
        self.dictionary_candidate_table.setMinimumHeight(0)
        self.dictionary_candidate_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.dictionary_candidate_table.setHorizontalHeaderLabels(["kind", "canonical", "value", "source", "status", "score", "reason"])
        self.dictionary_candidate_table.verticalHeader().setVisible(False)
        self.dictionary_candidate_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.dictionary_candidate_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.dictionary_candidate_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.dictionary_candidate_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.dictionary_candidate_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.dictionary_candidate_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.dictionary_candidate_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.dictionary_candidate_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.dictionary_tabs.addTab(self.dictionary_candidate_table, "自動候補")

        self.dictionary_term_table = QTableWidget(0, 5)
        self.dictionary_term_table.setMinimumHeight(0)
        self.dictionary_term_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.dictionary_term_table.setHorizontalHeaderLabels(["term", "quality", "occurrences", "sources", "examples"])
        self.dictionary_term_table.verticalHeader().setVisible(False)
        self.dictionary_term_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dictionary_term_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.dictionary_term_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.dictionary_term_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.dictionary_term_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.dictionary_term_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.dictionary_tabs.addTab(self.dictionary_term_table, "抽出語")

        self.dictionary_merge_preview = QPlainTextEdit()
        self.dictionary_merge_preview.setReadOnly(True)
        self.dictionary_tabs.addTab(self.dictionary_merge_preview, "Merge Preview")

        self.dictionary_evaluation_view = QPlainTextEdit()
        self.dictionary_evaluation_view.setReadOnly(True)
        self.dictionary_tabs.addTab(self.dictionary_evaluation_view, "Evaluation Report")

        self.dictionary_scan_result_table = QTableWidget(0, 5)
        self.dictionary_scan_result_table.setMinimumHeight(0)
        self.dictionary_scan_result_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.dictionary_scan_result_table.setHorizontalHeaderLabels(["source", "scanned", "text_items", "PII除外", "examples"])
        self.dictionary_scan_result_table.verticalHeader().setVisible(False)
        self.dictionary_scan_result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.dictionary_scan_result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.dictionary_scan_result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.dictionary_scan_result_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.dictionary_scan_result_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.dictionary_scan_result_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.dictionary_tabs.addTab(self.dictionary_scan_result_table, "Source Scan")

        return widget

    # ------------------------------------------------------------------
    # Data binding helpers
    # ------------------------------------------------------------------
    def _refresh_button_list(self, select_index: Optional[int] = None) -> None:
        self.button_list.clear()
        for button in self._manager.buttons:
            locked_prefix = '🔒 ' if not button.get('allow_delete', False) else ''
            selected_prefix = '★ ' if button.get('id') == self._dataset_desc_prompt_button_id else ''
            quick_prefix = '⚡ ' if button.get('id') == self._quick_ai_prompt_button_id else ''
            check_prefix = '📋 ' if button.get('id') == self._ai_check_prompt_button_id else ''
            icon = button.get('icon', '') or ''
            label = button.get('label', '(ラベル未設定)')

            target_kind = infer_ai_suggest_target_kind(button)
            target_tag = '［報告書］' if target_kind == 'report' else '［AI拡張］'
            item = QListWidgetItem(
                f"{selected_prefix}{quick_prefix}{check_prefix}{locked_prefix}{target_tag} {icon} {label} ({button.get('id', '???')})"
            )
            self.button_list.addItem(item)
        if self._manager.buttons:
            index = select_index if select_index is not None else min(self._current_index, len(self._manager.buttons) - 1)
            index = max(0, index)
            self.button_list.setCurrentRow(index)
        else:
            self._current_index = -1
            self._clear_form()
        self._update_button_controls()

    def _on_selection_changed(self, index: int) -> None:
        if self._is_loading_form:
            return
        self._save_current_button()
        self._current_index = index
        self._load_form(index)
        self._update_button_controls()

    def _load_form(self, index: int) -> None:
        self._is_loading_form = True
        try:
            if index < 0 or index >= len(self._manager.buttons):
                self._clear_form()
                return
            button = self._manager.buttons[index]
            self.id_edit.setText(button.get('id', ''))
            self.label_edit.setText(button.get('label', ''))
            self.icon_edit.setText(button.get('icon', ''))
            self.category_edit.setText(button.get('category', ''))
            self.prompt_file_edit.setText(button.get('prompt_file', ''))

            target_kind = infer_ai_suggest_target_kind(button)
            idx = self.target_kind_combo.findData(target_kind)
            if idx >= 0:
                self.target_kind_combo.setCurrentIndex(idx)
            else:
                self.target_kind_combo.setCurrentIndex(0)
            current_format = button.get('output_format', 'text')
            if self.output_format_combo.findText(current_format) == -1:
                self.output_format_combo.addItem(current_format)
            self.output_format_combo.setCurrentText(current_format)
            mode_value = button.get('prompt_assembly_mode', 'full_embed') or 'full_embed'
            mode_index = self.prompt_assembly_mode_combo.findData(mode_value)
            if mode_index < 0:
                mode_index = 0
            self.prompt_assembly_mode_combo.setCurrentIndex(mode_index)
            self.description_edit.setText(button.get('description', ''))
            self.prompt_template_edit.setText(button.get('prompt_template', ''))
            deletable = button.get('allow_delete', False)
            locked = button.get('id') in self._locked_ids
            self.allow_delete_checkbox.setChecked(deletable)
            self.allow_delete_checkbox.setEnabled(not locked)
            self.id_edit.setEnabled(not locked)

            # データセット説明AI提案のプロンプト指定
            button_id = button.get('id', '')
            is_selected = bool(button_id) and button_id == self._dataset_desc_prompt_button_id
            self.dataset_desc_prompt_checkbox.blockSignals(True)
            self.dataset_desc_prompt_checkbox.setChecked(is_selected)
            self.dataset_desc_prompt_checkbox.blockSignals(False)
            # json推奨: 明示的にjson以外は警告し、チェック操作時に弾く
            self.dataset_desc_prompt_checkbox.setEnabled(True)

            # QUICK AI のプロンプト指定
            is_quick_selected = bool(button_id) and button_id == self._quick_ai_prompt_button_id
            self.quick_ai_prompt_checkbox.blockSignals(True)
            self.quick_ai_prompt_checkbox.setChecked(is_quick_selected)
            self.quick_ai_prompt_checkbox.blockSignals(False)
            self.quick_ai_prompt_checkbox.setEnabled(True)

            # AI CHECK のプロンプト指定
            is_check_selected = bool(button_id) and button_id == self._ai_check_prompt_button_id
            self.ai_check_prompt_checkbox.blockSignals(True)
            self.ai_check_prompt_checkbox.setChecked(is_check_selected)
            self.ai_check_prompt_checkbox.blockSignals(False)
            self.ai_check_prompt_checkbox.setEnabled(True)
        finally:
            self._is_loading_form = False
        self._schedule_prompt_source_refresh(immediate=True)

    def _clear_form(self) -> None:
        self.id_edit.clear()
        self.label_edit.clear()
        self.icon_edit.clear()
        self.category_edit.clear()
        self.prompt_file_edit.clear()
        self.description_edit.clear()
        self.prompt_template_edit.clear()
        self._prompt_source_refresh_timer.stop()
        self._prompt_source_pending_request = None
        self.prompt_source_table.setRowCount(0)
        self.prompt_source_table.setEnabled(False)
        self.prompt_source_detail.clear()
        self.output_format_combo.setCurrentText("text")
        self.prompt_assembly_mode_combo.setCurrentIndex(0)
        self.target_kind_combo.setCurrentIndex(0)
        self.allow_delete_checkbox.setChecked(False)
        self.allow_delete_checkbox.setEnabled(False)
        self.id_edit.setEnabled(False)
        if hasattr(self, 'dataset_desc_prompt_checkbox'):
            self.dataset_desc_prompt_checkbox.blockSignals(True)
            self.dataset_desc_prompt_checkbox.setChecked(False)
            self.dataset_desc_prompt_checkbox.blockSignals(False)
            self.dataset_desc_prompt_checkbox.setEnabled(False)
        if hasattr(self, 'quick_ai_prompt_checkbox'):
            self.quick_ai_prompt_checkbox.blockSignals(True)
            self.quick_ai_prompt_checkbox.setChecked(False)
            self.quick_ai_prompt_checkbox.blockSignals(False)
            self.quick_ai_prompt_checkbox.setEnabled(False)
        if hasattr(self, 'ai_check_prompt_checkbox'):
            self.ai_check_prompt_checkbox.blockSignals(True)
            self.ai_check_prompt_checkbox.setChecked(False)
            self.ai_check_prompt_checkbox.blockSignals(False)
            self.ai_check_prompt_checkbox.setEnabled(False)

    def _save_current_button(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._manager.buttons):
            return
        button = self._manager.buttons[self._current_index]
        locked = button.get('id') in self._locked_ids
        if not locked:
            new_id = self.id_edit.text().strip()
            if new_id and new_id != button.get('id'):
                if self._manager.find_by_id(new_id) is not None:
                    QMessageBox.warning(self, "警告", "同じIDが既に存在します。IDは変更されません。")
                else:
                    button['id'] = new_id
        button['label'] = self.label_edit.text().strip()
        button['icon'] = self.icon_edit.text().strip() or '🤖'
        button['category'] = self.category_edit.text().strip()
        button['prompt_file'] = self.prompt_file_edit.text().strip()
        button['target_kind'] = self.target_kind_combo.currentData() or infer_ai_suggest_target_kind(button)
        button['output_format'] = self.output_format_combo.currentText()
        button['prompt_assembly_mode'] = self.prompt_assembly_mode_combo.currentData() or 'full_embed'
        button['prompt_assembly_sources'] = self._collect_prompt_source_overrides()
        button['description'] = self.description_edit.toPlainText().strip()
        button['prompt_template'] = self.prompt_template_edit.toPlainText().strip()
        if not locked:
            button['allow_delete'] = self.allow_delete_checkbox.isChecked()
        else:
            button['allow_delete'] = False

        # データセット説明AI提案のプロンプト指定は、選択されたボタンIDとして別キーで管理する
        # （ボタン定義自体にフラグを埋め込まない: 1つのみ・最後指定優先を確実にするため）
        try:
            button_id = button.get('id', '')
            if button_id and self.dataset_desc_prompt_checkbox.isChecked():
                self._dataset_desc_prompt_button_id = button_id
        except Exception:
            pass

        # QUICK AI のプロンプト指定
        try:
            button_id = button.get('id', '')
            if button_id and self.quick_ai_prompt_checkbox.isChecked():
                self._quick_ai_prompt_button_id = button_id
        except Exception:
            pass

        # AI CHECK のプロンプト指定
        try:
            button_id = button.get('id', '')
            if button_id and self.ai_check_prompt_checkbox.isChecked():
                self._ai_check_prompt_button_id = button_id
        except Exception:
            pass

    def _on_dataset_desc_prompt_toggled(self, checked: bool) -> None:
        if self._is_loading_form:
            return
        if not (0 <= self._current_index < len(self._manager.buttons)):
            return
        button = self._manager.buttons[self._current_index]
        button_id = (button.get('id') or '').strip()
        if not button_id:
            return
        # dataset説明AI提案はJSON前提のため、json以外は弾く（誤設定防止）
        fmt = (self.output_format_combo.currentText() or '').strip().lower()
        if checked and fmt != 'json':
            QMessageBox.warning(self, "警告", "データセット説明AI提案はJSON応答を前提とします。出力形式を 'json' にしてください。")
            self.dataset_desc_prompt_checkbox.blockSignals(True)
            self.dataset_desc_prompt_checkbox.setChecked(False)
            self.dataset_desc_prompt_checkbox.blockSignals(False)
            return

        if checked:
            # 最後に指定したものが優先（= これを選択）
            self._dataset_desc_prompt_button_id = button_id
        else:
            if self._dataset_desc_prompt_button_id == button_id:
                self._dataset_desc_prompt_button_id = ""

        # リストの★表示を更新
        self._refresh_button_list(select_index=self._current_index)

    def _on_quick_ai_prompt_toggled(self, checked: bool) -> None:
        if self._is_loading_form:
            return
        if not (0 <= self._current_index < len(self._manager.buttons)):
            return
        button = self._manager.buttons[self._current_index]
        button_id = (button.get('id') or '').strip()
        if not button_id:
            return

        if checked:
            self._quick_ai_prompt_button_id = button_id
        else:
            if self._quick_ai_prompt_button_id == button_id:
                self._quick_ai_prompt_button_id = ""

        self._refresh_button_list(select_index=self._current_index)

    def _on_ai_check_prompt_toggled(self, checked: bool) -> None:
        if self._is_loading_form:
            return
        if not (0 <= self._current_index < len(self._manager.buttons)):
            return
        button = self._manager.buttons[self._current_index]
        button_id = (button.get('id') or '').strip()
        if not button_id:
            return

        if checked:
            self._ai_check_prompt_button_id = button_id
        else:
            if self._ai_check_prompt_button_id == button_id:
                self._ai_check_prompt_button_id = ""

        self._refresh_button_list(select_index=self._current_index)

    def _update_button_controls(self) -> None:
        has_selection = 0 <= self._current_index < len(self._manager.buttons)
        self.delete_button.setEnabled(has_selection and self._manager.can_delete(self._current_index))
        self.move_up_button.setEnabled(has_selection and self._current_index > 0)
        self.move_down_button.setEnabled(has_selection and has_selection and self._current_index < len(self._manager.buttons) - 1)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_add_button(self) -> None:
        from qt_compat.widgets import QInputDialog

        self._save_current_button()
        button_id, ok = QInputDialog.getText(self, "AIサジェストボタンの追加", "新しいボタンのIDを入力してください")
        if not ok or not button_id.strip():
            return
        try:
            index = self._manager.add_button(button_id.strip())
            self._refresh_button_list(select_index=index)
        except ValueError as exc:
            QMessageBox.warning(self, "警告", str(exc))

    def _on_delete_button(self) -> None:
        if not (0 <= self._current_index < len(self._manager.buttons)):
            return
        button = self._manager.buttons[self._current_index]
        if not button.get('allow_delete', False):
            QMessageBox.information(self, "情報", "このボタンは削除できません。")
            return
        reply = QMessageBox.question(
            self,
            "確認",
            f"'{button.get('label', button.get('id'))}' を削除しますか？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._manager.remove_button(self._current_index)
            self._current_index = min(self._current_index, len(self._manager.buttons) - 1)
            self._refresh_button_list(select_index=self._current_index)
        except ValueError as exc:
            QMessageBox.warning(self, "警告", str(exc))

    def _move_selected(self, offset: int) -> None:
        if not (0 <= self._current_index < len(self._manager.buttons)):
            return
        new_index = self._current_index + offset
        if self._manager.move_button(self._current_index, new_index):
            self._current_index = new_index
            self._refresh_button_list(select_index=new_index)

    def _on_save(self) -> None:
        self._save_current_button()
        if self._prompt_dictionary_loaded:
            self._sync_prompt_dictionary_alias_rows()
            self._sync_prompt_dictionary_candidate_statuses()
        else:
            self._prompt_dictionary_config = load_prompt_dictionary_config()
        self._manager.set_dataset_description_ai_proposal_prompt_button_id(
            self._dataset_desc_prompt_button_id or None
        )
        self._manager.set_dataset_quick_ai_prompt_button_id(
            self._quick_ai_prompt_button_id or None
        )
        self._manager.set_dataset_ai_check_prompt_button_id(
            self._ai_check_prompt_button_id or None
        )
        success = self._manager.save()
        dictionary_saved = save_prompt_dictionary_config(self._prompt_dictionary_config)
        if success and dictionary_saved:
            QMessageBox.information(self, "保存完了", "AIサジェスト定義を保存しました。")
            self.config_saved.emit()
            self.accept()
        else:
            QMessageBox.critical(self, "エラー", "設定の保存に失敗しました。ログを確認してください。")

    def _schedule_prompt_source_refresh(self, *_args, immediate: bool = False) -> None:
        if self._is_loading_form:
            return
        self._prompt_source_request_seq += 1
        self._prompt_source_pending_request = {
            "request_id": self._prompt_source_request_seq,
            "inline_template": self.prompt_template_edit.toPlainText(),
            "prompt_file": self.prompt_file_edit.text().strip(),
        }
        self._set_prompt_source_loading_state("プロンプトテンプレートを解析中です。しばらくお待ちください。")
        if immediate:
            self._prompt_source_refresh_timer.stop()
            self._start_prompt_source_refresh()
        else:
            self._prompt_source_refresh_timer.start(_PROMPT_SOURCE_REFRESH_DELAY_MS)

    def _start_prompt_source_refresh(self) -> None:
        pending = self._prompt_source_pending_request
        if pending is None:
            return
        if self._prompt_source_preview_thread is not None and self._prompt_source_preview_thread.isRunning():
            return

        request_id = int(pending.get("request_id") or 0)
        inline_template = str(pending.get("inline_template") or "")
        prompt_file = str(pending.get("prompt_file") or "").strip()
        self._prompt_source_pending_request = None
        self._prompt_source_active_request_id = request_id

        if not inline_template.strip() and not prompt_file:
            self._populate_prompt_source_table([])
            return

        self._prompt_source_preview_thread = PromptSourcePreviewThread(
            request_id,
            inline_template=inline_template,
            prompt_file=prompt_file,
            parent=self,
        )
        self._prompt_source_preview_thread.preview_ready.connect(self._handle_prompt_source_preview_ready)
        self._prompt_source_preview_thread.error_occurred.connect(self._handle_prompt_source_preview_error)
        self._prompt_source_preview_thread.start()

    def _set_prompt_source_loading_state(self, message: str) -> None:
        self._source_mode_widgets = {}
        self.prompt_source_table.setRowCount(0)
        self.prompt_source_table.setEnabled(False)
        self.prompt_source_table.insertRow(0)
        loading_item = QTableWidgetItem(message)
        loading_item.setFlags(loading_item.flags() & ~Qt.ItemIsSelectable)
        self.prompt_source_table.setItem(0, 0, loading_item)
        for column_index in range(1, self.prompt_source_table.columnCount()):
            self.prompt_source_table.setItem(0, column_index, QTableWidgetItem(""))
        self.prompt_source_detail.setPlainText(message)

    def _populate_prompt_source_table(self, detected_sources: list[str]) -> None:
        self._source_mode_widgets = {}
        self.prompt_source_table.setRowCount(0)
        self.prompt_source_table.setEnabled(True)

        current_button = None
        if 0 <= self._current_index < len(self._manager.buttons):
            current_button = self._manager.buttons[self._current_index]
        source_overrides = {}
        if isinstance(current_button, dict):
            source_overrides = current_button.get('prompt_assembly_sources') or {}

        for row_index, placeholder in enumerate(detected_sources):
            metadata = self._prompt_source_catalog.get(placeholder, {})
            self.prompt_source_table.insertRow(row_index)

            label_item = QTableWidgetItem(f"{metadata.get('label', placeholder)} ({placeholder})")
            label_item.setData(Qt.UserRole, placeholder)
            self.prompt_source_table.setItem(row_index, 0, label_item)

            mode_combo = QComboBox()
            mode_combo.addItem("全文埋め込み", "full_embed")
            mode_combo.addItem("候補限定埋め込み", "filtered_embed")
            source_mode = (source_overrides.get(placeholder) or {}).get('mode') or current_button.get('prompt_assembly_mode', 'full_embed') if isinstance(current_button, dict) else 'full_embed'
            mode_index = mode_combo.findData(source_mode)
            mode_combo.setCurrentIndex(mode_index if mode_index >= 0 else 0)
            mode_combo.currentIndexChanged.connect(self._update_prompt_source_detail)
            self.prompt_source_table.setCellWidget(row_index, 1, mode_combo)
            self._source_mode_widgets[placeholder] = mode_combo

            method_item = QTableWidgetItem(metadata.get('method', ''))
            method_item.setToolTip(metadata.get('method', ''))
            self.prompt_source_table.setItem(row_index, 2, method_item)

            example_item = QTableWidgetItem(metadata.get('example', ''))
            example_item.setToolTip(metadata.get('example', ''))
            self.prompt_source_table.setItem(row_index, 3, example_item)

        if detected_sources:
            self.prompt_source_table.selectRow(0)
        else:
            self.prompt_source_detail.setPlainText("このテンプレートでは source ごとの巨大データプレースホルダは検出されませんでした。")

    def _handle_prompt_source_preview_ready(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        request_id = int(payload.get("request_id") or 0)
        thread = self._prompt_source_preview_thread
        self._prompt_source_preview_thread = None
        if thread is not None:
            thread.wait(500)
        if request_id != self._prompt_source_request_seq:
            if self._prompt_source_pending_request is not None:
                QTimer.singleShot(0, self._start_prompt_source_refresh)
            return
        self._populate_prompt_source_table(list(payload.get("detected_sources") or []))
        if self._prompt_source_pending_request is not None:
            QTimer.singleShot(0, self._start_prompt_source_refresh)

    def _handle_prompt_source_preview_error(self, error_message: str, request_id: int) -> None:
        thread = self._prompt_source_preview_thread
        self._prompt_source_preview_thread = None
        if thread is not None:
            thread.wait(500)
        if int(request_id or 0) != self._prompt_source_request_seq:
            if self._prompt_source_pending_request is not None:
                QTimer.singleShot(0, self._start_prompt_source_refresh)
            return
        self._source_mode_widgets = {}
        self.prompt_source_table.setRowCount(0)
        self.prompt_source_table.setEnabled(False)
        self.prompt_source_detail.setPlainText(error_message or "プロンプトテンプレートの解析に失敗しました。")
        if self._prompt_source_pending_request is not None:
            QTimer.singleShot(0, self._start_prompt_source_refresh)

    def _collect_prompt_source_overrides(self) -> dict:
        overrides = {}
        default_mode = self.prompt_assembly_mode_combo.currentData() or 'full_embed'
        for placeholder, combo in self._source_mode_widgets.items():
            mode_value = combo.currentData() or 'full_embed'
            if mode_value != default_mode:
                overrides[placeholder] = {'mode': mode_value}
        return overrides

    def _update_prompt_source_detail(self) -> None:
        current_row = self.prompt_source_table.currentRow()
        if current_row < 0:
            return
        item = self.prompt_source_table.item(current_row, 0)
        if item is None:
            return
        placeholder = item.data(Qt.UserRole)
        metadata = self._prompt_source_catalog.get(placeholder, {})
        mode_combo = self._source_mode_widgets.get(placeholder)
        mode_label = mode_combo.currentText() if mode_combo is not None else ""
        self.prompt_source_detail.setPlainText(
            f"対象: {metadata.get('label', placeholder)}\n"
            f"プレースホルダ: {placeholder}\n"
            f"現在の方式: {mode_label}\n\n"
            f"フィルター方法:\n{metadata.get('method', '')}\n\n"
            f"実例:\n{metadata.get('example', '')}"
        )

    def _sync_prompt_dictionary_candidate_statuses(self) -> None:
        candidates = ((self._prompt_dictionary_config.get("generated") or {}).get("candidates") or [])
        assist = self._prompt_dictionary_config.setdefault("assist", {})
        assist["web_enabled"] = self.dictionary_web_assist_checkbox.isChecked()
        assist["llm_enabled"] = self.dictionary_llm_assist_checkbox.isChecked()
        for candidate in candidates:
            combo = self._dictionary_candidate_status_widgets.get(candidate.get("id"))
            if combo is not None:
                candidate["status"] = combo.currentData() or "pending"
            row = combo.property("row") if combo is not None else None
            if row is None:
                continue
            canonical_item = self.dictionary_candidate_table.item(row, 1)
            value_item = self.dictionary_candidate_table.item(row, 2)
            source_item = self.dictionary_candidate_table.item(row, 3)
            reason_item = self.dictionary_candidate_table.item(row, 6)
            candidate["canonical"] = (canonical_item.text().strip() if canonical_item else candidate.get("canonical") or "")
            candidate["value"] = (value_item.text().strip() if value_item else candidate.get("value") or "")
            candidate["source"] = (source_item.text().strip() if source_item else candidate.get("source") or "")
            if reason_item is not None:
                candidate["reason"] = reason_item.text().strip()

    def _sync_prompt_dictionary_alias_rows(self) -> None:
        if not self._prompt_dictionary_loaded:
            return
        general_aliases = {}
        source_overrides = copy.deepcopy(self._prompt_dictionary_config.get("source_overrides") or {})
        for override in source_overrides.values():
            if isinstance(override, dict):
                override["aliases"] = {}

        for row_index in range(self.dictionary_alias_table.rowCount()):
            canonical_item = self.dictionary_alias_table.item(row_index, 0)
            aliases_item = self.dictionary_alias_table.item(row_index, 1)
            source_item = self.dictionary_alias_table.item(row_index, 2)
            canonical = (canonical_item.text().strip() if canonical_item else "")
            if not canonical:
                continue
            alias_values = self._split_alias_cell_text(aliases_item.text() if aliases_item else "")
            source = (source_item.text().strip() if source_item else "") or "global"
            if source.lower() in {"global", "default", "all"}:
                general_aliases[canonical] = alias_values
                continue
            override = source_overrides.setdefault(source, {})
            override.setdefault("aliases", {})
            override["aliases"][canonical] = alias_values

        self._prompt_dictionary_config["general_aliases"] = general_aliases
        self._prompt_dictionary_config["source_overrides"] = source_overrides

    def _split_alias_cell_text(self, text: str) -> list[str]:
        raw_tokens = []
        for chunk in str(text or "").replace("、", ",").replace(";", ",").splitlines():
            raw_tokens.extend(part.strip() for part in chunk.split(","))
        unique_tokens = []
        seen = set()
        for token in raw_tokens:
            if not token or token in seen:
                continue
            seen.add(token)
            unique_tokens.append(token)
        return unique_tokens

    def _on_add_dictionary_alias_row(self) -> None:
        if not self._prompt_dictionary_loaded:
            self._ensure_prompt_dictionary_loaded(force=True)
            return
        row_index = self.dictionary_alias_table.rowCount()
        self.dictionary_alias_table.insertRow(row_index)
        self.dictionary_alias_table.setItem(row_index, 0, QTableWidgetItem("new_term"))
        self.dictionary_alias_table.setItem(row_index, 1, QTableWidgetItem(""))
        self.dictionary_alias_table.setItem(row_index, 2, QTableWidgetItem("global"))
        self.dictionary_alias_table.selectRow(row_index)
        self.dictionary_alias_table.editItem(self.dictionary_alias_table.item(row_index, 0))

    def _on_remove_dictionary_alias_row(self) -> None:
        if not self._prompt_dictionary_loaded:
            return
        current_row = self.dictionary_alias_table.currentRow()
        if current_row < 0:
            return
        self.dictionary_alias_table.removeRow(current_row)

    def _on_prompt_dictionary_evaluate(self) -> None:
        if not self._prompt_dictionary_loaded:
            self._ensure_prompt_dictionary_loaded(force=True)
            return
        self._sync_prompt_dictionary_alias_rows()
        self._sync_prompt_dictionary_candidate_statuses()
        self._prompt_dictionary_config = evaluate_prompt_dictionary_benchmarks(self._prompt_dictionary_config)
        save_prompt_dictionary_config(self._prompt_dictionary_config)
        self._refresh_prompt_dictionary_views()

    def _on_prompt_dictionary_scan(self) -> None:
        if not self._prompt_dictionary_loaded:
            self._ensure_prompt_dictionary_loaded(force=True)
            return
        if self._dictionary_build_thread is not None and self._dictionary_build_thread.isRunning():
            return
        self._sync_prompt_dictionary_alias_rows()
        self._sync_prompt_dictionary_candidate_statuses()
        self._dictionary_progress_messages = []
        self.dictionary_progress_log.clear()
        self.dictionary_progress_label.setText("辞書作成を開始しました…")
        self.dictionary_progress_bar.setRange(0, 0)
        self.dictionary_progress_bar.setValue(0)
        self._set_prompt_dictionary_build_running(True)
        self._dictionary_build_thread = PromptDictionaryBuildThread(self._prompt_dictionary_config, max_files_per_source=2000, parent=self)
        self._dictionary_build_thread.progress_changed.connect(self._handle_prompt_dictionary_progress)
        self._dictionary_build_thread.result_ready.connect(self._handle_prompt_dictionary_scan_finished)
        self._dictionary_build_thread.error_occurred.connect(self._handle_prompt_dictionary_scan_error)
        self._dictionary_build_thread.start()

    def _on_prompt_dictionary_apply(self) -> None:
        if not self._prompt_dictionary_loaded:
            self._ensure_prompt_dictionary_loaded(force=True)
            return
        self._sync_prompt_dictionary_alias_rows()
        self._sync_prompt_dictionary_candidate_statuses()
        self._prompt_dictionary_config = apply_prompt_dictionary_candidates(self._prompt_dictionary_config)
        save_prompt_dictionary_config(self._prompt_dictionary_config)
        self._refresh_prompt_dictionary_views()

    def _set_prompt_dictionary_build_running(self, running: bool) -> None:
        ready = self._prompt_dictionary_loaded and not running and not (self._dictionary_load_thread and self._dictionary_load_thread.isRunning())
        self.dictionary_scan_button.setEnabled(ready)
        self.dictionary_apply_button.setEnabled(ready)
        self.dictionary_evaluate_button.setEnabled(ready)
        self.dictionary_web_assist_checkbox.setEnabled(ready)
        self.dictionary_llm_assist_checkbox.setEnabled(ready)
        self.dictionary_add_alias_button.setEnabled(ready)
        self.dictionary_remove_alias_button.setEnabled(ready)
        self.dictionary_alias_table.setEnabled(ready)

    def _on_editor_tab_changed(self, index: int) -> None:
        if self.editor_tabs.widget(index) is self._dictionary_tab:
            self._ensure_prompt_dictionary_loaded()

    def _ensure_prompt_dictionary_loaded(self, force: bool = False) -> None:
        if self._prompt_dictionary_loaded:
            return
        if self._dictionary_load_thread is not None and self._dictionary_load_thread.isRunning():
            return
        if not force and self.editor_tabs.currentWidget() is not self._dictionary_tab:
            return
        self.dictionary_progress_label.setText("辞書を読み込み中…")
        self.dictionary_progress_bar.setRange(0, 0)
        self.dictionary_progress_log.setPlainText("巨大な辞書本体は辞書タブを開いた時だけ非同期で読み込みます。")
        self._set_prompt_dictionary_build_running(True)
        self._dictionary_load_thread = PromptDictionaryLoadThread(parent=self)
        self._dictionary_load_thread.loaded.connect(self._handle_prompt_dictionary_load_finished)
        self._dictionary_load_thread.error_occurred.connect(self._handle_prompt_dictionary_load_error)
        self._dictionary_load_thread.start()

    def _handle_prompt_dictionary_load_finished(self, _summary: dict) -> None:
        thread = self._dictionary_load_thread
        self._prompt_dictionary_config = thread.result_config if thread is not None else {}
        self._prompt_dictionary_loaded = True
        self.dictionary_progress_bar.setRange(0, 1)
        self.dictionary_progress_bar.setValue(1)
        self.dictionary_progress_label.setText("辞書の読み込みが完了しました。")
        self._dictionary_load_thread = None
        if thread is not None:
            thread.wait(500)
        self._set_prompt_dictionary_build_running(False)
        self._refresh_prompt_dictionary_views()

    def _handle_prompt_dictionary_load_error(self, error_message: str) -> None:
        thread = self._dictionary_load_thread
        self._dictionary_load_thread = None
        if thread is not None:
            thread.wait(500)
        self._set_prompt_dictionary_build_running(False)
        self.dictionary_progress_bar.setRange(0, 1)
        self.dictionary_progress_bar.setValue(0)
        self.dictionary_progress_label.setText("辞書の読み込みに失敗しました。")
        self.dictionary_progress_log.setPlainText(error_message or "辞書の読み込みに失敗しました。")

    def _handle_prompt_dictionary_progress(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        message = str(payload.get("message") or "辞書作成中")
        current = payload.get("current")
        total = payload.get("total")
        candidate_count = payload.get("candidate_count")
        extracted_term_count = payload.get("extracted_term_count")
        suffix = []
        if candidate_count is not None:
            suffix.append(f"candidates={candidate_count}")
        if extracted_term_count is not None:
            suffix.append(f"terms={extracted_term_count}")
        if suffix:
            message = f"{message} ({', '.join(suffix)})"
        self.dictionary_progress_label.setText(message)
        if isinstance(current, int) and isinstance(total, int) and total > 0:
            self.dictionary_progress_bar.setRange(0, total)
            self.dictionary_progress_bar.setValue(min(current, total))
        else:
            self.dictionary_progress_bar.setRange(0, 0)
        if not self._dictionary_progress_messages or self._dictionary_progress_messages[-1] != message:
            self._dictionary_progress_messages.append(message)
            self._dictionary_progress_messages = self._dictionary_progress_messages[-120:]
            self.dictionary_progress_log.setPlainText("\n".join(self._dictionary_progress_messages))
            cursor = self.dictionary_progress_log.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.dictionary_progress_log.setTextCursor(cursor)

    def _handle_prompt_dictionary_scan_finished(self, _summary: dict) -> None:
        self._set_prompt_dictionary_build_running(False)
        self.dictionary_progress_bar.setRange(0, 1)
        self.dictionary_progress_bar.setValue(1)
        self.dictionary_progress_label.setText("辞書作成が完了しました。")
        thread = self._dictionary_build_thread
        if thread is not None and isinstance(thread.result_config, dict):
            self._prompt_dictionary_config = thread.result_config
            self._prompt_dictionary_loaded = True
        save_prompt_dictionary_config(self._prompt_dictionary_config)
        self._refresh_prompt_dictionary_views()
        self._dictionary_build_thread = None
        if thread is not None:
            thread.wait(500)

    def _handle_prompt_dictionary_scan_error(self, error_message: str) -> None:
        self._set_prompt_dictionary_build_running(False)
        self.dictionary_progress_bar.setRange(0, 1)
        self.dictionary_progress_bar.setValue(0)
        self.dictionary_progress_label.setText("辞書作成に失敗しました。")
        if error_message:
            self._dictionary_progress_messages.append(f"ERROR: {error_message}")
            self._dictionary_progress_messages = self._dictionary_progress_messages[-120:]
            self.dictionary_progress_log.setPlainText("\n".join(self._dictionary_progress_messages))
        QMessageBox.warning(self, "辞書作成エラー", error_message or "辞書作成に失敗しました。")
        thread = self._dictionary_build_thread
        self._dictionary_build_thread = None
        if thread is not None:
            thread.wait(500)

    def _refresh_prompt_dictionary_views(self) -> None:
        summary = get_prompt_dictionary_summary(self._prompt_dictionary_config if self._prompt_dictionary_loaded else {})
        scan_results = ((self._prompt_dictionary_config.get("generated") or {}).get("scan_results") or [])
        recursive_scan_sources = sum(1 for item in scan_results if str(item.get("source") or "").endswith("_recursive"))
        self.dictionary_web_assist_checkbox.setChecked(bool(summary.get("web_enabled")))
        self.dictionary_llm_assist_checkbox.setChecked(bool(summary.get("llm_enabled")))
        self.dictionary_summary_view.setPlainText(
            "\n".join(
                [
                    f"general_aliases: {summary.get('general_alias_count', 0)}",
                    f"source_aliases: {summary.get('source_alias_count', 0)}",
                    f"stopwords: {summary.get('stopword_count', 0)}",
                    f"weak_stopwords: {summary.get('weak_stopword_count', 0)}",
                    f"allowlist: {summary.get('allowlist_count', 0)}",
                    f"generated candidates: {summary.get('candidate_count', 0)}",
                    f"extracted terms: {summary.get('extracted_term_count', 0)}",
                    f"auto approved: {summary.get('auto_approved_candidate_count', 0)}",
                    f"status counts: {summary.get('status_counts', {})}",
                    f"web assist: {'ON' if summary.get('web_enabled') else 'OFF'}",
                    f"llm assist: {'ON' if summary.get('llm_enabled') else 'OFF'}",
                    f"recursive scan sources: {recursive_scan_sources}",
                    f"dictionary loaded: {'YES' if self._prompt_dictionary_loaded else 'NO'}",
                    f"display limits: aliases={_PROMPT_DICTIONARY_ALIAS_VIEW_LIMIT}, candidates={_PROMPT_DICTIONARY_CANDIDATE_VIEW_LIMIT}, terms={_PROMPT_DICTIONARY_TERM_VIEW_LIMIT}",
                    f"last scanned: {summary.get('last_scanned_at', '') or '(未実行)'}",
                    f"last applied: {summary.get('last_applied_at', '') or '(未適用)'}",
                ]
            )
        )

        alias_rows = []
        for canonical, values in sorted((self._prompt_dictionary_config.get("general_aliases") or {}).items()):
            alias_rows.append((canonical, ", ".join(values or []), "global"))
        for source_key, override in sorted((self._prompt_dictionary_config.get("source_overrides") or {}).items()):
            for canonical, values in sorted((override.get("aliases") or {}).items()):
                alias_rows.append((canonical, ", ".join(values or []), source_key))
        alias_rows = alias_rows[:_PROMPT_DICTIONARY_ALIAS_VIEW_LIMIT]
        self.dictionary_alias_table.setUpdatesEnabled(False)
        self.dictionary_alias_table.setRowCount(0)
        self.dictionary_alias_table.setRowCount(len(alias_rows))
        for row_index, row in enumerate(alias_rows):
            for column_index, value in enumerate(row):
                self.dictionary_alias_table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        self.dictionary_alias_table.setUpdatesEnabled(True)

        stopword_rows = [
            ("stopword", self._summarize_token_list(self._prompt_dictionary_config.get("stopwords") or []), "global"),
            ("weak_stopword", self._summarize_token_list(self._prompt_dictionary_config.get("weak_stopwords") or []), "global"),
            ("allowlist", self._summarize_token_list(self._prompt_dictionary_config.get("allowlist") or []), "global"),
        ]
        for source_key, override in sorted((self._prompt_dictionary_config.get("source_overrides") or {}).items()):
            stopword_rows.append(("stopword", self._summarize_token_list(override.get("stopwords") or []), source_key))
            stopword_rows.append(("weak_stopword", self._summarize_token_list(override.get("weak_stopwords") or []), source_key))
            stopword_rows.append(("allowlist", self._summarize_token_list(override.get("allowlist") or []), source_key))
        self.dictionary_stopword_table.setUpdatesEnabled(False)
        self.dictionary_stopword_table.setRowCount(0)
        self.dictionary_stopword_table.setRowCount(len(stopword_rows))
        for row_index, row in enumerate(stopword_rows):
            for column_index, value in enumerate(row):
                self.dictionary_stopword_table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        self.dictionary_stopword_table.setUpdatesEnabled(True)

        source_override_rows = list(sorted((self._prompt_dictionary_config.get("source_overrides") or {}).items()))
        self.dictionary_source_override_table.setUpdatesEnabled(False)
        self.dictionary_source_override_table.setRowCount(0)
        self.dictionary_source_override_table.setRowCount(len(source_override_rows))
        for row_index, (source_key, override) in enumerate(source_override_rows):
            values = [
                source_key,
                str(len(override.get("aliases") or {})),
                str(len(override.get("stopwords") or [])),
                str(len(override.get("weak_stopwords") or [])),
                str(len(override.get("allowlist") or [])),
            ]
            for column_index, value in enumerate(values):
                self.dictionary_source_override_table.setItem(row_index, column_index, QTableWidgetItem(value))
        self.dictionary_source_override_table.setUpdatesEnabled(True)

        self._dictionary_candidate_status_widgets = {}
        candidates = ((self._prompt_dictionary_config.get("generated") or {}).get("candidates") or [])
        visible_candidates = list(candidates[:_PROMPT_DICTIONARY_CANDIDATE_VIEW_LIMIT])
        self.dictionary_candidate_table.setUpdatesEnabled(False)
        self.dictionary_candidate_table.setRowCount(0)
        self.dictionary_candidate_table.setRowCount(len(visible_candidates))
        for row_index, candidate in enumerate(visible_candidates):
            static_values = [
                candidate.get("kind") or "",
                candidate.get("canonical") or "",
                candidate.get("value") or "",
                candidate.get("source") or "",
            ]
            for column_index, value in enumerate(static_values):
                item = QTableWidgetItem(str(value))
                if column_index in {1, 2, 3, 6}:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.dictionary_candidate_table.setItem(row_index, column_index, item)
            status_combo = QComboBox()
            for label, status in [("pending", "pending"), ("approved", "approved"), ("applied", "applied"), ("rejected", "rejected")]:
                status_combo.addItem(label, status)
            status_index = status_combo.findData(candidate.get("status") or "pending")
            status_combo.setCurrentIndex(status_index if status_index >= 0 else 0)
            status_combo.setProperty("row", row_index)
            self.dictionary_candidate_table.setCellWidget(row_index, 4, status_combo)
            self._dictionary_candidate_status_widgets[candidate.get("id")] = status_combo
            score_item = QTableWidgetItem(str(candidate.get("score") or ""))
            score_item.setFlags(score_item.flags() & ~Qt.ItemIsEditable)
            self.dictionary_candidate_table.setItem(row_index, 5, score_item)
            reason = candidate.get("reason") or ""
            examples = "; ".join(candidate.get("examples") or [])
            reason_item = self.dictionary_candidate_table.item(row_index, 6)
            if reason_item is None:
                reason_item = QTableWidgetItem()
                reason_item.setFlags(reason_item.flags() | Qt.ItemIsEditable)
                self.dictionary_candidate_table.setItem(row_index, 6, reason_item)
            reason_item.setText(f"{reason} | {examples}".strip(" |"))
        self.dictionary_candidate_table.setUpdatesEnabled(True)

        visible_terms = ((self._prompt_dictionary_config.get("generated") or {}).get("term_inventory") or [])[:_PROMPT_DICTIONARY_TERM_VIEW_LIMIT]
        self.dictionary_term_table.setUpdatesEnabled(False)
        self.dictionary_term_table.setRowCount(0)
        self.dictionary_term_table.setRowCount(len(visible_terms))
        for row_index, item in enumerate(visible_terms):
            values = [
                item.get("term") or "",
                str(item.get("quality_score") or 0),
                str(item.get("occurrences") or 0),
                str(item.get("source_count") or 0),
                " | ".join(item.get("examples") or []),
            ]
            for column_index, value in enumerate(values):
                self.dictionary_term_table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        self.dictionary_term_table.setUpdatesEnabled(True)

        merge_preview = build_prompt_dictionary_merge_preview(self._prompt_dictionary_config)
        self.dictionary_merge_preview.setPlainText(self._truncate_json_preview(merge_preview))

        evaluation = ((self._prompt_dictionary_config.get("generated") or {}).get("evaluation_report") or {})
        self.dictionary_evaluation_view.setPlainText(self._truncate_json_preview(evaluation))

        scan_result_rows = list((self._prompt_dictionary_config.get("generated") or {}).get("scan_results") or [])
        self.dictionary_scan_result_table.setUpdatesEnabled(False)
        self.dictionary_scan_result_table.setRowCount(0)
        self.dictionary_scan_result_table.setRowCount(len(scan_result_rows))
        for row_index, result in enumerate(scan_result_rows):
            values = [
                result.get("source") or "",
                str(result.get("scanned_items") or 0),
                str(result.get("text_items") or 0),
                str(result.get("pii_filtered_items") or 0),
                " | ".join((result.get("top_terms") or [])[:3]) or " | ".join(result.get("examples") or []),
            ]
            for column_index, value in enumerate(values):
                self.dictionary_scan_result_table.setItem(row_index, column_index, QTableWidgetItem(value))
        self.dictionary_scan_result_table.setUpdatesEnabled(True)

    def _summarize_token_list(self, values: list[str]) -> str:
        tokens = [str(value) for value in (values or []) if str(value)]
        if len(tokens) <= _PROMPT_DICTIONARY_LIST_TEXT_LIMIT:
            return ", ".join(tokens)
        visible = ", ".join(tokens[:_PROMPT_DICTIONARY_LIST_TEXT_LIMIT])
        return f"{visible} ... (+{len(tokens) - _PROMPT_DICTIONARY_LIST_TEXT_LIMIT})"

    def _truncate_json_preview(self, payload: dict) -> str:
        text = json.dumps(payload or {}, ensure_ascii=False, indent=2)
        if len(text) <= _PROMPT_DICTIONARY_JSON_PREVIEW_MAX_CHARS:
            return text
        omitted = len(text) - _PROMPT_DICTIONARY_JSON_PREVIEW_MAX_CHARS
        return f"{text[:_PROMPT_DICTIONARY_JSON_PREVIEW_MAX_CHARS]}\n... truncated {omitted} chars ..."

    def _apply_dialog_size_policy(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        min_height = max(360, int(available.height() * 0.5))
        self.setMinimumHeight(min_height)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_dialog_size_policy()

    def closeEvent(self, event) -> None:
        self._prompt_source_refresh_timer.stop()
        for thread in (
            self._prompt_source_preview_thread,
            self._dictionary_load_thread,
            self._dictionary_build_thread,
        ):
            if thread is not None and thread.isRunning():
                thread.wait(1000)
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _apply_button_theme(self, button: QPushButton, bg_key: ThemeKey) -> None:
        button.setStyleSheet(
            f"QPushButton {{ background-color: {get_color(bg_key)}; color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};"
            f" border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; border-radius: 4px; padding: 6px 10px; }}"
            f"QPushButton:disabled {{ background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};"
            f" color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)}; }}"
        )
