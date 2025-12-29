"""
TAGビルダーダイアログ

データセット編集でのTAG設定を支援するダイアログ
- 自由記述入力
- プリセット値からの選択（MI.jsonベース）
- 将来的にAIサジェスト・他データセットからのコピー機能を拡張予定
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel, 
    QListWidget, QListWidgetItem, QTextEdit, QGroupBox, QCheckBox,
    QMessageBox, QScrollArea, QWidget, QSplitter, QLineEdit, QTreeWidget,
    QTreeWidgetItem, QTabWidget, QComboBox, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView, QProgressBar
)
from qt_compat.core import Qt, Signal, QThread
from classes.theme import get_color, ThemeKey
from classes.ai.core.ai_manager import AIManager
from classes.dataset.util.dataset_context_collector import get_dataset_context_collector
from classes.dataset.util.ai_extension_helper import load_prompt_file, format_prompt_with_context

# ロガー設定
logger = logging.getLogger(__name__)


_CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def parse_tag_suggestion_response(response_text: str) -> List[Dict[str, Any]]:
    """AI応答テキストからタグ提案(JSON配列)を抽出して返す。"""
    if not response_text:
        return []
    text = response_text.strip()

    match = _CODE_BLOCK_PATTERN.search(text)
    if match:
        text = match.group(1).strip()

    candidates = [text]
    first_bracket = text.find('[')
    last_bracket = text.rfind(']')
    if first_bracket != -1 and last_bracket > first_bracket:
        candidates.append(text[first_bracket:last_bracket + 1])

    parsed: Any = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue

    if not isinstance(parsed, list):
        return []

    results: List[Dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        label = item.get('label')
        if isinstance(label, str) and label.strip():
            results.append(item)
    return results


class TagSuggestionRequestThread(QThread):
    """TAG提案AIリクエスト用スレッド"""

    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt

    def run(self):
        try:
            from classes.config.ui.ai_settings_widget import get_ai_config

            ai_config = get_ai_config()
            provider = ai_config.get('default_provider', 'gemini') if ai_config else 'gemini'
            model = (
                ai_config.get('providers', {}).get(provider, {}).get('default_model', 'gemini-2.0-flash')
                if ai_config else 'gemini-2.0-flash'
            )

            ai_manager = AIManager()
            result = ai_manager.send_prompt(self.prompt, provider, model)
            if result.get('success', False):
                self.result_ready.emit(result)
            else:
                self.error_occurred.emit(result.get('error', '不明なエラー'))
        except Exception as e:
            self.error_occurred.emit(str(e))


class TagBuilderDialog(QDialog):
    """TAGビルダーダイアログ"""
    
    # TAGが変更されたときのシグナル
    tags_changed = Signal(str)
    
    def __init__(
        self,
        parent=None,
        current_tags: str = "",
        dataset_id: Optional[str] = None,
        dataset_context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(parent)
        self.current_tags = current_tags
        self.selected_tags = []
        self.preset_data = {}
        self.dataset_id = dataset_id
        self.dataset_context = dataset_context or {}
        self._ai_thread: Optional[TagSuggestionRequestThread] = None
        self._last_ai_prompt: str = ""
        self._last_ai_response_text: str = ""
        
        # プリセットデータを読み込み
        self.load_preset_data()
        
        self.init_ui()
        self.parse_current_tags()

        # テーマ変更に追従
        try:
            from classes.theme.theme_manager import ThemeManager
            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        except Exception:
            pass
        self.refresh_theme()
    
    def load_preset_data(self):
        """MI.jsonからプリセットデータを読み込み"""
        try:
            from config.common import INPUT_DIR
            mi_json_path = os.path.join(INPUT_DIR, "ai", "MI.json")
            
            if os.path.exists(mi_json_path):
                logger.debug("MI.jsonを読み込み: %s", mi_json_path)
                
                with open(mi_json_path, 'r', encoding='utf-8') as f:
                    self.preset_data = json.load(f)
                
                logger.debug("プリセットデータ読み込み完了: %sカテゴリ", len(self.preset_data))
                for category, subcategories in self.preset_data.items():
                    if isinstance(subcategories, dict):
                        total_items = sum(len(items) for items in subcategories.values() if isinstance(items, list))
                        logger.debug("- %s: %s項目", category, total_items)
            else:
                logger.warning("MI.jsonが見つかりません: %s", mi_json_path)
                self.set_default_preset_data()
                    
        except Exception as e:
            logger.error("MI.json読み込みエラー: %s", e)
            self.set_default_preset_data()
    
    def set_default_preset_data(self):
        """デフォルトのプリセットデータを設定"""
        self.preset_data = {
            "基本タグ": {
                "分析手法": [
                    "XRD", "SEM", "TEM", "XPS", "FTIR", "Raman",
                    "AFM", "STM", "NMR", "ESR", "UV-Vis"
                ],
                "材料分類": [
                    "金属", "セラミックス", "ポリマー", "複合材料",
                    "ナノマテリアル", "薄膜", "バルク材料"
                ],
                "処理方法": [
                    "焼成", "焼結", "スパッタリング", "CVD", "PVD",
                    "ゾルゲル", "電析", "機械加工"
                ]
            }
        }
    
    def init_ui(self):
        """UIを初期化"""
        self.setWindowTitle("TAGビルダー")
        self.setModal(True)
        self.resize(800, 600)
        
        # メインレイアウト
        main_layout = QVBoxLayout()
        
        # タブウィジェット
        self.tab_widget = QTabWidget()
        
        # 1. 自由記述タブ
        free_input_tab = self.create_free_input_tab()
        self.tab_widget.addTab(free_input_tab, "自由記述")
        
        # 2. プリセットタブ
        preset_tab = self.create_preset_tab()
        self.tab_widget.addTab(preset_tab, "プリセット選択")

        # 3. AI提案タブ
        ai_tab = self.create_ai_suggest_tab()
        self.tab_widget.addTab(ai_tab, "AI提案")
        
        main_layout.addWidget(self.tab_widget)
        
        # プレビューエリア
        preview_group = QGroupBox("選択されたTAG")
        preview_layout = QVBoxLayout()
        
        self.selected_tags_list = QListWidget()
        self.selected_tags_list.setMaximumHeight(120)
        preview_layout.addWidget(self.selected_tags_list)
        
        # プレビューテキスト
        self.preview_text = QLineEdit()
        self.preview_text.setPlaceholderText("タグがカンマ区切りで表示されます")
        self.preview_text.setReadOnly(True)
        preview_layout.addWidget(QLabel("最終出力:"))
        preview_layout.addWidget(self.preview_text)
        
        preview_group.setLayout(preview_layout)
        main_layout.addWidget(preview_group)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        
        clear_button = QPushButton("クリア")
        clear_button.clicked.connect(self.clear_all_tags)
        button_layout.addWidget(clear_button)
        
        button_layout.addStretch()
        
        cancel_button = QPushButton("キャンセル")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.accept_tags)
        ok_button.setDefault(True)
        button_layout.addWidget(ok_button)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def create_free_input_tab(self):
        """自由記述タブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 説明
        info_label = QLabel("TAGを自由に入力できます。カンマ区切りで複数のタグを入力してください。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 入力エリア
        self.free_input_edit = QTextEdit()
        self.free_input_edit.setPlaceholderText("例: TEM観察, 電子回折, ナノ構造, 結晶解析")
        self.free_input_edit.setMaximumHeight(150)
        self.free_input_edit.textChanged.connect(self.on_free_input_changed)
        layout.addWidget(self.free_input_edit)
        
        # 追加ボタン
        add_button = QPushButton("入力内容を追加")
        add_button.clicked.connect(self.add_free_input_tags)
        layout.addWidget(add_button)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_preset_tab(self):
        """プリセットタブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 説明
        info_label = QLabel("MI.jsonに基づくプリセットタグから選択できます。大項目・中項目・小項目すべて選択可能です。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 統計情報
        self.stats_label = QLabel()
        self.update_stats_label()
        layout.addWidget(self.stats_label)
        
        # カテゴリ選択
        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("カテゴリ:"))
        
        self.category_combo = QComboBox()
        self.category_combo.currentTextChanged.connect(self.on_category_changed)
        category_layout.addWidget(self.category_combo)
        
        layout.addLayout(category_layout)
        
        # 検索機能
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("検索:"))
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("タグを検索...")
        self.search_edit.textChanged.connect(self.on_search_text_changed)
        search_layout.addWidget(self.search_edit)
        
        clear_search_button = QPushButton("クリア")
        clear_search_button.setMaximumWidth(60)
        clear_search_button.clicked.connect(lambda: self.search_edit.clear())
        search_layout.addWidget(clear_search_button)
        
        layout.addLayout(search_layout)
        
        # ツリービュー
        self.preset_tree = QTreeWidget()
        self.preset_tree.setHeaderLabels(["項目"])
        self.preset_tree.itemChanged.connect(self.on_preset_item_changed)
        self.preset_tree.itemDoubleClicked.connect(self.on_preset_item_double_clicked)
        layout.addWidget(self.preset_tree)
        
        # プリセットデータを表示
        self.populate_preset_data()
        
        widget.setLayout(layout)
        return widget

    def create_ai_suggest_tab(self):
        """AI提案タブを作成"""
        widget = QWidget()
        layout = QVBoxLayout()

        info_label = QLabel(
            "選択中データセットを対象にAIへ問い合わせ、TAG候補を提示します。\n"
            "候補を選択して『採用』すると、下部のTAG一覧へ追加されます。"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        target_text = self._build_ai_target_summary_text()
        self.ai_target_label = QLabel(target_text)
        self.ai_target_label.setWordWrap(True)
        layout.addWidget(self.ai_target_label)

        button_layout = QHBoxLayout()
        self.ai_generate_button = QPushButton("AI提案取得")
        self.ai_generate_button.clicked.connect(self.on_ai_generate_clicked)
        button_layout.addWidget(self.ai_generate_button)

        self.ai_prompt_button = QPushButton("プロンプト全文")
        self.ai_prompt_button.setEnabled(False)
        self.ai_prompt_button.clicked.connect(self.on_ai_show_prompt_clicked)
        button_layout.addWidget(self.ai_prompt_button)

        self.ai_response_button = QPushButton("回答全文")
        self.ai_response_button.setEnabled(False)
        self.ai_response_button.clicked.connect(self.on_ai_show_response_clicked)
        button_layout.addWidget(self.ai_response_button)

        self.ai_apply_button = QPushButton("選択を採用")
        self.ai_apply_button.clicked.connect(self.on_ai_apply_clicked)
        self.ai_apply_button.setEnabled(False)
        button_layout.addWidget(self.ai_apply_button)

        self.ai_apply_all_button = QPushButton("全て採用")
        self.ai_apply_all_button.clicked.connect(self.on_ai_apply_all_clicked)
        self.ai_apply_all_button.setEnabled(False)
        button_layout.addWidget(self.ai_apply_all_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.ai_progress = QProgressBar()
        self.ai_progress.setRange(0, 0)
        self.ai_progress.setVisible(False)
        layout.addWidget(self.ai_progress)

        self.ai_suggestions_table = QTableWidget(0, 3)
        self.ai_suggestions_table.setHorizontalHeaderLabels(["rank", "label", "reason"])
        self.ai_suggestions_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ai_suggestions_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.ai_suggestions_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.ai_suggestions_table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.ai_suggestions_table)

        widget.setLayout(layout)
        return widget

    def _build_ai_target_summary_text(self) -> str:
        if not self.dataset_id:
            return "対象データセット: （未選択）"
        name = str(self.dataset_context.get('name') or '')
        grant_number = str(self.dataset_context.get('grant_number') or '')
        parts = ["対象データセット:"]
        if name:
            parts.append(f"- 名前: {name}")
        parts.append(f"- ID: {self.dataset_id}")
        if grant_number:
            parts.append(f"- 課題番号: {grant_number}")
        return "\n".join(parts)

    def refresh_theme(self):
        """テーマ変更時の再描画/スタイル適用"""
        try:
            if hasattr(self, 'stats_label') and self.stats_label is not None:
                self.stats_label.setStyleSheet(
                    f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 11px;"
                )
        except Exception:
            pass

        try:
            if hasattr(self, 'preset_tree') and self.preset_tree is not None:
                self.preset_tree.setStyleSheet(
                    "\n".join(
                        [
                            f"QTreeWidget {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }}",
                            f"QTreeView::indicator {{ width:16px; height:16px; border:1px solid {get_color(ThemeKey.INPUT_BORDER)}; background:{get_color(ThemeKey.INPUT_BACKGROUND)}; border-radius:3px; }}",
                            f"QTreeView::indicator:checked {{ background:{get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; border-color:{get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; }}",
                        ]
                    )
                )
        except Exception:
            pass
    
    def update_stats_label(self):
        """統計情報ラベルを更新"""
        if not self.preset_data:
            self.stats_label.setText("プリセットデータなし")
            return
        
        total_categories = len(self.preset_data)
        total_items = 0
        
        for category_data in self.preset_data.values():
            if isinstance(category_data, dict):
                for items in category_data.values():
                    if isinstance(items, list):
                        total_items += len(items)
        
        stats_text = f"利用可能: {total_categories}カテゴリ, {total_items}項目"
        self.stats_label.setText(stats_text)
        try:
            self.stats_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 11px;")
        except Exception:
            pass

    def on_ai_generate_clicked(self):
        """AI提案を実行"""
        if self._ai_thread is not None and self._ai_thread.isRunning():
            return

        if not self.dataset_id:
            QMessageBox.information(self, "AI提案", "AI提案は、データセット選択時のみ利用できます。")
            return

        template = load_prompt_file('input/ai/prompts/json/json_suggest_tag_rde.txt')
        if not template:
            QMessageBox.warning(self, "AI提案", "プロンプトテンプレートの読み込みに失敗しました。")
            return

        # データセットコンテキストを収集
        try:
            collector = get_dataset_context_collector()
            full_context = collector.collect_full_context(dataset_id=self.dataset_id, **self.dataset_context)
        except Exception as e:
            QMessageBox.warning(self, "AI提案", f"データセット情報の収集に失敗しました:\n{e}")
            return

        prompt = format_prompt_with_context(template, full_context)
        self._last_ai_prompt = prompt
        self._last_ai_response_text = ""
        self.ai_prompt_button.setEnabled(bool(self._last_ai_prompt.strip()))
        self.ai_response_button.setEnabled(False)

        self.ai_generate_button.setEnabled(False)
        self.ai_apply_button.setEnabled(False)
        self.ai_apply_all_button.setEnabled(False)
        self.ai_progress.setVisible(True)

        self._ai_thread = TagSuggestionRequestThread(prompt)
        self._ai_thread.result_ready.connect(self._on_ai_result_ready)
        self._ai_thread.error_occurred.connect(self._on_ai_error)
        self._ai_thread.finished.connect(self._on_ai_finished)
        self._ai_thread.start()

    def _on_ai_finished(self):
        self.ai_progress.setVisible(False)
        self.ai_generate_button.setEnabled(True)
        self._ai_thread = None

    def _on_ai_error(self, error_message: str):
        reply = QMessageBox.question(
            self,
            "AI提案",
            f"AI問い合わせに失敗しました。\n\n{error_message}\n\n再試行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self.on_ai_generate_clicked()

    def _on_ai_result_ready(self, result: object):
        try:
            if isinstance(result, dict):
                response_text = result.get('response') or result.get('content', '')
            else:
                response_text = ''

            # ログ保存（結果一覧タブで参照できるようにする）
            try:
                from classes.dataset.util.ai_suggest_result_log import append_result

                append_result(
                    target_kind='dataset',
                    target_key=str(self.dataset_id or '').strip() or 'unknown',
                    button_id='tag_suggest',
                    button_label='TAG提案',
                    prompt=self._last_ai_prompt,
                    display_format='text',
                    display_content=str(response_text or ''),
                    provider=(result.get('provider') if isinstance(result, dict) else None),
                    model=(result.get('model') if isinstance(result, dict) else None),
                    request_params=(result.get('request_params') if isinstance(result, dict) else None),
                    response_params=(result.get('response_params') if isinstance(result, dict) else None),
                    started_at=(result.get('started_at') if isinstance(result, dict) else None),
                    finished_at=(result.get('finished_at') if isinstance(result, dict) else None),
                    elapsed_seconds=(result.get('elapsed_seconds') if isinstance(result, dict) else None),
                )
            except Exception:
                pass

            self._last_ai_response_text = str(response_text)
            self.ai_response_button.setEnabled(bool(self._last_ai_response_text.strip()))

            suggestions = parse_tag_suggestion_response(str(response_text))
            if not suggestions:
                reply = QMessageBox.question(
                    self,
                    "AI提案",
                    "TAG候補を解析できませんでした（JSON配列が必要です）。\n\n再試行しますか？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                self.ai_suggestions_table.setRowCount(0)
                self.ai_apply_button.setEnabled(False)
                self.ai_apply_all_button.setEnabled(False)
                if reply == QMessageBox.Yes:
                    self.on_ai_generate_clicked()
                return

            self.ai_suggestions_table.setRowCount(0)
            for item in suggestions:
                rank = str(item.get('rank', ''))
                label = str(item.get('label', '')).strip()
                reason = str(item.get('reason', '')).strip()
                if not label:
                    continue

                row = self.ai_suggestions_table.rowCount()
                self.ai_suggestions_table.insertRow(row)
                self.ai_suggestions_table.setItem(row, 0, QTableWidgetItem(rank))
                label_item = QTableWidgetItem(label)
                label_item.setData(Qt.UserRole, label)
                self.ai_suggestions_table.setItem(row, 1, label_item)
                self.ai_suggestions_table.setItem(row, 2, QTableWidgetItem(reason))

            has_rows = self.ai_suggestions_table.rowCount() > 0
            self.ai_apply_button.setEnabled(has_rows)
            self.ai_apply_all_button.setEnabled(has_rows)
        except Exception as e:
            QMessageBox.warning(self, "AI提案", f"AI応答の処理に失敗しました:\n{e}")
            self.ai_suggestions_table.setRowCount(0)
            self.ai_apply_button.setEnabled(False)
            self.ai_apply_all_button.setEnabled(False)

    def on_ai_show_prompt_clicked(self):
        self._show_text_dialog("AI提案: プロンプト全文", self._last_ai_prompt)

    def on_ai_show_response_clicked(self):
        self._show_text_dialog("AI提案: 回答全文", self._last_ai_response_text)

    def _show_text_dialog(self, title: str, text: str):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.resize(800, 600)

        layout = QVBoxLayout(dialog)
        edit = QTextEdit()
        edit.setReadOnly(True)
        edit.setPlainText(text or "")
        layout.addWidget(edit)

        buttons = QHBoxLayout()
        buttons.addStretch()
        close_button = QPushButton("閉じる")
        close_button.clicked.connect(dialog.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        dialog.exec()

    def on_ai_apply_clicked(self):
        """選択したAI提案をTAGに反映"""
        if not hasattr(self, 'ai_suggestions_table'):
            return
        selection = self.ai_suggestions_table.selectionModel()
        if selection is None:
            return

        rows = {index.row() for index in selection.selectedRows()}
        if not rows:
            return

        added = False
        for row in sorted(rows):
            item = self.ai_suggestions_table.item(row, 1)
            if item is None:
                continue
            label = item.data(Qt.UserRole) or item.text()
            if isinstance(label, str):
                label = label.strip()
            if not label:
                continue
            if label not in self.selected_tags:
                self.selected_tags.append(label)
                added = True

        if added:
            self.update_preview()
            self.update_preset_checkboxes()

    def on_ai_apply_all_clicked(self):
        """AI提案の全候補をTAGに反映"""
        if not hasattr(self, 'ai_suggestions_table'):
            return

        row_count = self.ai_suggestions_table.rowCount()
        if row_count <= 0:
            return

        added = False
        for row in range(row_count):
            item = self.ai_suggestions_table.item(row, 1)
            if item is None:
                continue
            label = item.data(Qt.UserRole) or item.text()
            if isinstance(label, str):
                label = label.strip()
            if not label:
                continue
            if label not in self.selected_tags:
                self.selected_tags.append(label)
                added = True

        if added:
            self.update_preview()
            self.update_preset_checkboxes()
    
    def populate_preset_data(self):
        """プリセットデータをツリーに表示"""
        self.category_combo.clear()
        
        if not self.preset_data:
            self.category_combo.addItem("データなし")
            return
        
        # カテゴリを追加
        self.category_combo.addItem("全て表示")
        for category in self.preset_data.keys():
            self.category_combo.addItem(category)
        
        # 全てのデータを表示
        self.update_preset_tree("全て表示")
    
    def on_category_changed(self, category):
        """カテゴリ選択変更時の処理"""
        self.update_preset_tree(category)
    
    def on_search_text_changed(self, search_text):
        """検索テキスト変更時の処理"""
        self.filter_preset_tree(search_text.strip().lower())
    
    def filter_preset_tree(self, search_text):
        """検索テキストに基づいてツリーをフィルター"""
        if not search_text:
            # 検索テキストが空の場合、全て表示
            for i in range(self.preset_tree.topLevelItemCount()):
                self.show_tree_item_recursive(self.preset_tree.topLevelItem(i), True)
            return
        
        # 検索テキストに一致する項目のみ表示
        for i in range(self.preset_tree.topLevelItemCount()):
            category_item = self.preset_tree.topLevelItem(i)
            category_has_match = self.filter_tree_item_recursive(category_item, search_text)
            category_item.setHidden(not category_has_match)
    
    def filter_tree_item_recursive(self, item, search_text):
        """ツリーアイテムを再帰的にフィルター"""
        has_match = False
        
        # 現在のアイテムのテキストをチェック
        item_text = item.text(0).lower()
        current_match = search_text in item_text
        
        # 子アイテムをチェック
        for i in range(item.childCount()):
            child = item.child(i)
            child_has_match = self.filter_tree_item_recursive(child, search_text)
            child.setHidden(not child_has_match)
            
            if child_has_match:
                has_match = True
        
        # 現在のアイテムまたは子にマッチがある場合は表示
        if current_match or has_match:
            item.setHidden(False)
            return True
        else:
            item.setHidden(True)
            return False
    
    def show_tree_item_recursive(self, item, show):
        """ツリーアイテムの表示/非表示を再帰的に設定"""
        item.setHidden(not show)
        for i in range(item.childCount()):
            self.show_tree_item_recursive(item.child(i), show)
    
    def update_preset_tree(self, selected_category):
        """プリセットツリーを更新"""
        self.preset_tree.clear()
        
        if not self.preset_data:
            return
        
        if selected_category == "全て表示":
            categories_to_show = self.preset_data.keys()
        else:
            categories_to_show = [selected_category] if selected_category in self.preset_data else []
        
        for category in categories_to_show:
            category_data = self.preset_data[category]
            if not isinstance(category_data, dict):
                continue
            
            category_item = QTreeWidgetItem([category])
            category_item.setExpanded(True)
            # 大項目も選択可能にする
            category_item.setFlags(category_item.flags() | Qt.ItemIsUserCheckable)
            category_item.setCheckState(0, Qt.Unchecked)
            self.preset_tree.addTopLevelItem(category_item)
            
            for subcategory, items in category_data.items():
                if not isinstance(items, list):
                    continue
                
                subcategory_item = QTreeWidgetItem([subcategory])
                subcategory_item.setExpanded(True)
                # 中項目も選択可能にする
                subcategory_item.setFlags(subcategory_item.flags() | Qt.ItemIsUserCheckable)
                subcategory_item.setCheckState(0, Qt.Unchecked)
                category_item.addChild(subcategory_item)
                
                for item in items:
                    item_widget = QTreeWidgetItem([item])
                    item_widget.setFlags(item_widget.flags() | Qt.ItemIsUserCheckable)
                    item_widget.setCheckState(0, Qt.Unchecked)
                    subcategory_item.addChild(item_widget)
        
        # 現在選択されているタグにチェックを入れる
        self.update_preset_checkboxes()
    
    def update_preset_checkboxes(self):
        """現在のタグ状態に基づいてチェックボックスを更新"""
        for i in range(self.preset_tree.topLevelItemCount()):
            category_item = self.preset_tree.topLevelItem(i)
            self.update_tree_item_checkboxes(category_item)
    
    def update_tree_item_checkboxes(self, item):
        """ツリーアイテムのチェックボックスを再帰的に更新"""
        # 全ての項目（大項目、中項目、小項目）をチェック
        tag_text = item.text(0)
        if tag_text in self.selected_tags:
            item.setCheckState(0, Qt.CheckState.Checked)
        else:
            item.setCheckState(0, Qt.CheckState.Unchecked)
        
        # 子アイテムも再帰的にチェック
        for i in range(item.childCount()):
            child = item.child(i)
            self.update_tree_item_checkboxes(child)
    
    def on_preset_item_changed(self, item, column):
        """プリセット項目の選択変更時の処理"""
        tag_text = item.text(0)
        
        # checkState()はenumを返すが、整数値比較の方が安全
        if item.checkState(0).value == 2:  # Qt.CheckState.Checked.value
            if tag_text not in self.selected_tags:
                self.selected_tags.append(tag_text)
        else:
            if tag_text in self.selected_tags:
                self.selected_tags.remove(tag_text)
        
        self.update_preview()
    
    def on_preset_item_double_clicked(self, item, column):
        """プリセット項目のダブルクリック時の処理"""
        tag_text = item.text(0)
        
        # ダブルクリックで選択状態を切り替え
        if tag_text in self.selected_tags:
            self.selected_tags.remove(tag_text)
            item.setCheckState(0, Qt.CheckState.Unchecked)
        else:
            self.selected_tags.append(tag_text)
            item.setCheckState(0, Qt.CheckState.Checked)
        
        self.update_preview()
    
    def on_free_input_changed(self):
        """自由入力テキスト変更時の処理"""
        # リアルタイムでプレビューは更新しない（追加ボタン押下時のみ）
        pass
    
    def add_free_input_tags(self):
        """自由入力からタグを追加"""
        input_text = self.free_input_edit.toPlainText().strip()
        if not input_text:
            return
        
        # カンマ区切りで分割
        new_tags = [tag.strip() for tag in input_text.split(',') if tag.strip()]
        
        # 重複を避けて追加
        for tag in new_tags:
            if tag not in self.selected_tags:
                self.selected_tags.append(tag)
        
        # 入力欄をクリア
        self.free_input_edit.clear()
        
        # プレビュー更新
        self.update_preview()
        
        # プリセットのチェックボックスも更新
        self.update_preset_checkboxes()
    
    def parse_current_tags(self):
        """現在のタグ文字列を解析してリストに設定"""
        if not self.current_tags:
            return
        
        # カンマ区切りで分割
        tags = [tag.strip() for tag in self.current_tags.split(',') if tag.strip()]
        self.selected_tags = tags
        
        # プレビューを更新
        self.update_preview()
        
        # プリセットのチェックボックスを更新
        self.update_preset_checkboxes()
        
        logger.debug("現在のタグを解析: %s", tags)
    
    def update_preview(self):
        """プレビューを更新"""
        # リストウィジェットを更新
        self.selected_tags_list.clear()
        for tag in self.selected_tags:
            item = QListWidgetItem(tag)
            self.selected_tags_list.addItem(item)
        
        # テキストプレビューを更新
        tags_text = ", ".join(self.selected_tags)
        self.preview_text.setText(tags_text)
    
    def clear_all_tags(self):
        """全てのタグをクリア"""
        reply = QMessageBox.question(
            self, "確認", 
            "選択されているタグを全てクリアしますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.selected_tags.clear()
            self.update_preview()
            self.update_preset_checkboxes()
    
    def accept_tags(self):
        """TAGを確定"""
        tags_text = ", ".join(self.selected_tags)
        self.tags_changed.emit(tags_text)
        self.accept()
    
    def get_tags_string(self):
        """タグ文字列を取得"""
        return ", ".join(self.selected_tags)


def test_tag_builder():
    """TAGビルダーのテスト用関数"""
    import sys
    from qt_compat.widgets import QApplication
    
    app = QApplication(sys.argv)
    
    # テスト用の初期タグ
    current_tags = "TEM観察, 電子回折"
    
    dialog = TagBuilderDialog(current_tags=current_tags)
    
    def on_tags_changed(tags):
        logger.debug("タグが変更されました: %s", tags)
    
    dialog.tags_changed.connect(on_tags_changed)
    
    if dialog.exec() == QDialog.Accepted:
        result = dialog.get_tags_string()
        logger.debug("最終結果: %s", result)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    test_tag_builder()
