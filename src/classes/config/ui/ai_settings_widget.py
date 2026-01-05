"""
AI設定ウィジェット - ARIM RDE Tool
AIテスト機能用のLLM設定を管理するウィジェット

機能:
- プロバイダー（OpenAI、Gemini、ローカルLLM）の設定
- モデル選択
- API Key設定
- ローカルLLM URL設定
- 設定の保存・読み込み
"""

import json
import os
import logging
from typing import Dict, Any, List, Optional

from classes.theme import get_color, ThemeKey

from classes.ai.util.generation_params import (
    GENERATION_PARAM_SPECS,
    build_gemini_generate_content_body,
    build_openai_chat_completions_payload,
    normalize_ai_config_inplace,
    parse_stop_sequences,
)

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox,
        QGroupBox, QGridLayout, QScrollArea, QTextEdit,
        QSpinBox, QDoubleSpinBox, QMessageBox, QFormLayout,
        QProgressBar, QSplitter, QTableWidget, QTableWidgetItem,
        QHeaderView, QRadioButton, QButtonGroup
    )
    from qt_compat.core import Qt, Signal, QThread
    from qt_compat.gui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    # ダミークラス定義
    class QWidget: pass
    class Signal: pass

# ログ設定
logger = logging.getLogger(__name__)

# パス管理
try:
    from config.common import get_dynamic_file_path
except ImportError:
    def get_dynamic_file_path(relative_path):
        return relative_path

class AISettingsWidget(QWidget):
    """AI設定ウィジェット"""
    
    # シグナル定義
    settings_changed = Signal()
    
    def __init__(self, parent=None, use_internal_scroll: bool = True):
        super().__init__(parent)
        self.parent_widget = parent
        self._use_internal_scroll = use_internal_scroll
        self.config_file_path = get_dynamic_file_path("input/ai_config.json")
        self.current_config = {}
        # モデル一覧の元データと価格キャッシュ
        self._models_master: Dict[str, List[str]] = {}
        # Geminiは認証方式ごとにモデル一覧/デフォルトを保持
        self._gemini_models_by_auth_ui: Dict[str, Dict[str, Any]] = {}
        self._gemini_current_auth_mode: str = 'api_key'
        self._pricing_cache: Dict[str, Dict[str, str]] = {}
        # 取得処理の多重実行防止とスレッド参照
        self._fetch_inflight: set[str] = set()
        self._workers: Dict[str, "QThread"] = {}
        self._progress_boxes: Dict[str, "QMessageBox"] = {}
        
        # UI要素の参照
        self.provider_widgets = {}
        self.default_provider_combo = None
        self.timeout_spinbox = None
        self.request_max_attempts_spinbox = None
        self.max_tokens_spinbox = None  # 互換性のため残す（UIでは使用しない）
        self.temperature_spinbox = None  # 互換性のため残す（UIでは使用しない）

        # 生成パラメータ（新UI）
        self.generation_params_table = None
        self._gen_param_controls: Dict[str, Dict[str, Any]] = {}
        
        self.setup_ui()
        self.load_current_settings()
    
    def setup_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # タイトル
        title_label = QLabel("AI設定")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(15)
        
        # グローバル設定
        self.setup_global_settings(content_layout)

        # 生成パラメータ設定（グローバルの下に追加）
        self.setup_generation_params_settings(content_layout)
        
        # プロバイダー設定
        self.setup_provider_settings(content_layout)
        
        # テスト機能
        self.setup_test_section(content_layout)

        if self._use_internal_scroll:
            # スクロールエリア（単体利用向け）
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll_area.setWidget(content_widget)
            layout.addWidget(scroll_area, 1)
        else:
            # 親側（設定タブ側）でスクロール制御する場合は内部スクロールを作らない
            try:
                from qt_compat.widgets import QSizePolicy
                content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            except Exception:
                pass
            layout.addWidget(content_widget, 1)
        
        # ボタンエリア
        self.setup_buttons(layout)
    
    def setup_global_settings(self, layout):
        """グローバル設定セクション"""
        group = QGroupBox("グローバル設定")
        group_layout = QFormLayout(group)
        
        # デフォルトプロバイダー
        self.default_provider_combo = QComboBox()
        self.default_provider_combo.addItems(["openai", "gemini", "local_llm"])
        group_layout.addRow("デフォルトプロバイダー:", self.default_provider_combo)
        
        # タイムアウト
        self.timeout_spinbox = QSpinBox()
        self.timeout_spinbox.setRange(1, 300)
        self.timeout_spinbox.setValue(30)
        self.timeout_spinbox.setSuffix(" 秒")
        group_layout.addRow("タイムアウト:", self.timeout_spinbox)

        # リトライ回数（最大試行回数）
        self.request_max_attempts_spinbox = QSpinBox()
        self.request_max_attempts_spinbox.setRange(1, 5)
        self.request_max_attempts_spinbox.setValue(3)
        self.request_max_attempts_spinbox.setSuffix(" 回")
        self.request_max_attempts_spinbox.setToolTip(
            "AI API問い合わせが失敗した場合の最大試行回数（既定3回、最大5回）"
        )
        group_layout.addRow("問い合わせ最大試行回数:", self.request_max_attempts_spinbox)
        
        layout.addWidget(group)

    def setup_generation_params_settings(self, layout):
        """生成パラメータ設定セクション（プロバイダ差異は送信時に吸収）"""
        group = QGroupBox("生成パラメータ")
        group_layout = QVBoxLayout(group)

        desc = QLabel(
            "各パラメータは『カスタム使用』をONにした場合のみリクエストに含めます。\n"
            "OFFの場合は未指定（プロバイダ/モデルのデフォルト動作）になります。"
        )
        desc.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 11px;")
        group_layout.addWidget(desc)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["パラメータ", "説明", "値", "カスタム使用"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setWordWrap(True)

        table.setRowCount(len(GENERATION_PARAM_SPECS))

        self._gen_param_controls.clear()

        for row, spec in enumerate(GENERATION_PARAM_SPECS):
            label_item = QTableWidgetItem(spec.label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, label_item)

            desc_item = QTableWidgetItem(spec.description)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 1, desc_item)

            if spec.value_type == "float":
                value_widget = QDoubleSpinBox()
                value_widget.setDecimals(3)
                if spec.min_value is not None and spec.max_value is not None:
                    value_widget.setRange(float(spec.min_value), float(spec.max_value))
                value_widget.setSingleStep(0.05)
                value_widget.setValue(float(spec.default_value))
            elif spec.value_type == "int":
                value_widget = QSpinBox()
                if spec.min_value is not None and spec.max_value is not None:
                    value_widget.setRange(int(spec.min_value), int(spec.max_value))
                value_widget.setValue(int(spec.default_value))
            else:
                value_widget = QLineEdit()
                value_widget.setPlaceholderText("例: END, ###")

            use_checkbox = QCheckBox()
            use_checkbox.setChecked(False)

            table.setCellWidget(row, 2, value_widget)
            table.setCellWidget(row, 3, use_checkbox)

            self._gen_param_controls[spec.key] = {"value": value_widget, "use_custom": use_checkbox}

        table.resizeRowsToContents()
        table.setMinimumHeight(260)

        self.generation_params_table = table
        group_layout.addWidget(table)
        layout.addWidget(group)
    
    def setup_provider_settings(self, layout):
        """プロバイダー設定セクション"""
        # OpenAI設定
        self.setup_openai_settings(layout)
        
        # Gemini設定
        self.setup_gemini_settings(layout)
        
        # ローカルLLM設定
        self.setup_local_llm_settings(layout)
    
    def setup_openai_settings(self, layout):
        """OpenAI設定"""
        group = QGroupBox("OpenAI設定")
        group_layout = QVBoxLayout(group)

        # 折りたたみヘッダ（常に表示）
        header_layout = QHBoxLayout()
        toggle_button = QPushButton("▶")
        toggle_button.setMaximumWidth(24)
        toggle_button.setToolTip("復元")
        header_layout.addWidget(toggle_button)

        enabled_checkbox = QCheckBox("OpenAIを有効にする")
        header_layout.addWidget(enabled_checkbox)

        default_model_label = QLabel("デフォルトモデル:")
        header_layout.addWidget(default_model_label)

        default_model_combo = QComboBox()
        default_model_combo.setEditable(True)
        initial_models = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"]
        self._update_default_model_combo(default_model_combo, initial_models, 'openai', 'gpt-4o-mini')
        header_layout.addWidget(default_model_combo)
        header_layout.addStretch()
        group_layout.addLayout(header_layout)

        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)

        # 設定フォーム（詳細）
        form_layout = QFormLayout()

        # API Key
        api_key_edit = QLineEdit()
        api_key_edit.setEchoMode(QLineEdit.Password)
        api_key_edit.setPlaceholderText("OpenAI API Keyを入力...")
        form_layout.addRow("API Key:", api_key_edit)

        # Base URL
        base_url_edit = QLineEdit()
        base_url_edit.setText("https://api.openai.com/v1")
        form_layout.addRow("Base URL:", base_url_edit)
        
        # 利用可能モデルラベルと更新ボタン + フィルタ
        models_header_layout = QHBoxLayout()
        models_label = QLabel("利用可能モデル:")
        models_header_layout.addWidget(models_label)
        
        # フィルタ入力
        models_filter = QLineEdit()
        models_filter.setPlaceholderText("フィルタ（例: gpt-4o）")
        models_filter.setMaximumWidth(180)
        models_filter.textChanged.connect(lambda _: self._apply_models_filter('openai'))
        models_header_layout.addWidget(models_filter)
        
        clear_filter_btn = QPushButton("解除")
        clear_filter_btn.setMaximumWidth(50)
        clear_filter_btn.clicked.connect(lambda: self._clear_models_filter('openai'))
        models_header_layout.addWidget(clear_filter_btn)
        
        # モデル更新ボタン
        fetch_models_button = QPushButton("🔄 APIから取得")
        fetch_models_button.setToolTip("OpenAI APIから利用可能なモデルリストを取得")
        fetch_models_button.setMaximumWidth(120)
        fetch_models_button.clicked.connect(lambda: self.fetch_available_models('openai'))
        models_header_layout.addWidget(fetch_models_button)
        models_header_layout.addStretch()
        
        form_layout.addRow(models_header_layout)
        
        # モデル一覧テーブル
        models_table = QTableWidget()
        models_table.setColumnCount(3)
        models_table.setHorizontalHeaderLabels(["デフォルト", "モデル名", "料金情報"])
        models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        models_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        models_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        models_table.setMaximumHeight(200)
        models_table.setSelectionMode(QTableWidget.NoSelection)
        models_table.verticalHeader().setVisible(False)
        
        # 初期モデルをテーブルに追加
        initial_models = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"]
        self._populate_models_table(models_table, initial_models, 'openai', 'gpt-4o-mini')
        
        form_layout.addRow("", models_table)
        
        # 価格参照リンク
        pricing_link = QLabel('<a href="https://platform.openai.com/docs/pricing">📊 OpenAI公式価格ページ</a>')
        pricing_link.setOpenExternalLinks(True)
        pricing_link.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_LINK)}; font-size: 11px;")
        form_layout.addRow("", pricing_link)

        details_layout.addLayout(form_layout)
        details_widget.setVisible(False)  # デフォルトは縮小
        group_layout.addWidget(details_widget)
        
        # ウィジェット参照を保存
        self.provider_widgets['openai'] = {
            'enabled': enabled_checkbox,
            'api_key': api_key_edit,
            'base_url': base_url_edit,
            'default_model': default_model_combo,
            'models_table': models_table,
            'fetch_button': fetch_models_button,
            'filter': models_filter,
            'clear_filter': clear_filter_btn,
            'toggle_button': toggle_button,
            'details_widget': details_widget,
        }

        toggle_button.clicked.connect(lambda: self._toggle_provider_details('openai'))
        
        layout.addWidget(group)
    
    def setup_gemini_settings(self, layout):
        """Gemini設定"""
        group = QGroupBox("Gemini設定")
        group_layout = QVBoxLayout(group)

        # 折りたたみヘッダ（常に表示）
        header_layout = QHBoxLayout()
        toggle_button = QPushButton("▶")
        toggle_button.setMaximumWidth(24)
        toggle_button.setToolTip("復元")
        header_layout.addWidget(toggle_button)

        enabled_checkbox = QCheckBox("Geminiを有効にする")
        header_layout.addWidget(enabled_checkbox)

        default_model_label = QLabel("デフォルトモデル:")
        header_layout.addWidget(default_model_label)

        default_model_combo = QComboBox()
        default_model_combo.setEditable(True)
        initial_models = ["gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"]
        self._update_default_model_combo(default_model_combo, initial_models, 'gemini', 'gemini-2.0-flash-exp')
        header_layout.addWidget(default_model_combo)
        header_layout.addStretch()
        group_layout.addLayout(header_layout)

        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)

        # 設定フォーム（詳細）
        form_layout = QFormLayout()

        # 認証方式
        auth_mode_combo = QComboBox()
        auth_mode_combo.addItem("APIキー", 'api_key')
        auth_mode_combo.addItem("Vertex AI（サービスアカウントJSON）", 'vertex_sa')
        form_layout.addRow("認証方式:", auth_mode_combo)

        # API Key
        api_key_edit = QLineEdit()
        api_key_edit.setEchoMode(QLineEdit.Password)
        api_key_edit.setPlaceholderText("Gemini API Keyを入力...")
        form_layout.addRow("API Key:", api_key_edit)

        # VertexサービスアカウントJSON
        vertex_json_row = QHBoxLayout()
        vertex_json_edit = QLineEdit()
        vertex_json_edit.setReadOnly(True)
        vertex_json_edit.setPlaceholderText("サービスアカウントJSON（.json）を選択...")
        vertex_json_row.addWidget(vertex_json_edit, 1)
        vertex_json_browse = QPushButton("参照...")
        vertex_json_browse.setMaximumWidth(80)
        vertex_json_row.addWidget(vertex_json_browse)
        form_layout.addRow("SA JSON:", vertex_json_row)

        vertex_project_edit = QLineEdit()
        vertex_project_edit.setPlaceholderText("例: my-gcp-project（未入力ならJSON内 project_id を使用）")
        form_layout.addRow("Vertex Project:", vertex_project_edit)

        vertex_location_edit = QLineEdit()
        vertex_location_edit.setPlaceholderText("例: asia-northeast1")
        vertex_location_edit.setText("asia-northeast1")
        form_layout.addRow("Vertex Location:", vertex_location_edit)

        # Base URL
        base_url_edit = QLineEdit()
        base_url_edit.setText("https://generativelanguage.googleapis.com/v1beta")
        form_layout.addRow("Base URL:", base_url_edit)
        
        # 利用可能モデルラベルと更新ボタン + フィルタ
        models_header_layout = QHBoxLayout()
        models_label = QLabel("利用可能モデル:")
        models_header_layout.addWidget(models_label)
        
        # フィルタ入力
        models_filter = QLineEdit()
        models_filter.setPlaceholderText("フィルタ（例: gemini-1.5）")
        models_filter.setMaximumWidth(180)
        models_filter.textChanged.connect(lambda _: self._apply_models_filter('gemini'))
        models_header_layout.addWidget(models_filter)
        
        clear_filter_btn = QPushButton("解除")
        clear_filter_btn.setMaximumWidth(50)
        clear_filter_btn.clicked.connect(lambda: self._clear_models_filter('gemini'))
        models_header_layout.addWidget(clear_filter_btn)
        
        # モデル更新ボタン
        fetch_models_button = QPushButton("🔄 APIから取得")
        fetch_models_button.setToolTip("Gemini APIから利用可能なモデルリストを取得")
        fetch_models_button.setMaximumWidth(120)
        fetch_models_button.clicked.connect(lambda: self.fetch_available_models('gemini'))
        models_header_layout.addWidget(fetch_models_button)
        models_header_layout.addStretch()
        
        form_layout.addRow(models_header_layout)
        
        # モデル一覧テーブル
        models_table = QTableWidget()
        models_table.setColumnCount(3)
        models_table.setHorizontalHeaderLabels(["デフォルト", "モデル名", "料金情報"])
        models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        models_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        models_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        models_table.setMaximumHeight(200)
        models_table.setSelectionMode(QTableWidget.NoSelection)
        models_table.verticalHeader().setVisible(False)
        
        # 初期モデルをテーブルに追加
        initial_models = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"]
        self._populate_models_table(models_table, initial_models, 'gemini', 'gemini-2.0-flash')
        
        form_layout.addRow("", models_table)
        
        # 価格参照リンク
        pricing_link = QLabel('<a href="https://ai.google.dev/gemini-api/docs/pricing?hl=ja">📊 Gemini公式価格ページ</a>')
        pricing_link.setOpenExternalLinks(True)
        pricing_link.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_LINK)}; font-size: 11px;")
        form_layout.addRow("", pricing_link)

        details_layout.addLayout(form_layout)
        details_widget.setVisible(False)  # デフォルトは縮小
        group_layout.addWidget(details_widget)
        
        # ウィジェット参照を保存
        self.provider_widgets['gemini'] = {
            'enabled': enabled_checkbox,
            'auth_mode': auth_mode_combo,
            'api_key': api_key_edit,
            'vertex_service_account_json': vertex_json_edit,
            'vertex_browse': vertex_json_browse,
            'vertex_project_id': vertex_project_edit,
            'vertex_location': vertex_location_edit,
            'base_url': base_url_edit,
            'default_model': default_model_combo,
            'models_table': models_table,
            'fetch_button': fetch_models_button,
            'filter': models_filter,
            'clear_filter': clear_filter_btn,
            'toggle_button': toggle_button,
            'details_widget': details_widget,
        }

        def _get_current_gemini_models_from_table() -> List[str]:
            try:
                tbl = self.provider_widgets.get('gemini', {}).get('models_table')
                if not tbl:
                    return []
                models: List[str] = []
                for row in range(tbl.rowCount()):
                    item = tbl.item(row, 1)
                    if not item:
                        continue
                    # 表示名ではなく、セルテキスト（表示用解決済み）を採用していた既存仕様に合わせる
                    models.append(item.text())
                return [m for m in models if isinstance(m, str) and m.strip()]
            except Exception:
                return []

        def _stash_gemini_ui_state(mode: str):
            try:
                mode_key = str(mode or 'api_key')
                models = _get_current_gemini_models_from_table()
                default_model = default_model_combo.currentText().strip() if default_model_combo else ''
                self._gemini_models_by_auth_ui[mode_key] = {
                    'models': list(models),
                    'default_model': default_model,
                }
            except Exception:
                return

        def _restore_gemini_ui_state(mode: str):
            mode_key = str(mode or 'api_key')
            entry = self._gemini_models_by_auth_ui.get(mode_key) or {}
            models = entry.get('models') if isinstance(entry, dict) else None
            default_model = entry.get('default_model') if isinstance(entry, dict) else None
            if not isinstance(models, list):
                models = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"]
            if not isinstance(default_model, str) or not default_model.strip():
                default_model = "gemini-2.0-flash"

            # テーブルを再構築
            try:
                self._populate_models_table(models_table, models, 'gemini', default_model)
                self._update_default_model_combo(default_model_combo, models, 'gemini', default_model)
            except Exception:
                pass

            # フィルタ解除時に戻せるようマスターも更新
            try:
                self._models_master[self._get_models_master_key('gemini')] = list(models)
            except Exception:
                pass

        def _apply_gemini_auth_mode_ui():
            mode = auth_mode_combo.currentData() or 'api_key'
            use_vertex = str(mode) == 'vertex_sa'

            # モード切替前のUI状態を退避し、切替先を復元
            try:
                prev = getattr(self, '_gemini_current_auth_mode', 'api_key')
                prev = str(prev or 'api_key')
                nxt = str(mode or 'api_key')
                if prev != nxt:
                    _stash_gemini_ui_state(prev)
                    self._gemini_current_auth_mode = nxt
                    _restore_gemini_ui_state(nxt)
            except Exception:
                self._gemini_current_auth_mode = str(mode or 'api_key')

            # 入力欄の有効/無効
            api_key_edit.setEnabled(not use_vertex)
            base_url_edit.setEnabled(not use_vertex)
            fetch_models_button.setEnabled(True)

            vertex_json_edit.setEnabled(use_vertex)
            vertex_json_browse.setEnabled(use_vertex)
            vertex_project_edit.setEnabled(use_vertex)
            vertex_location_edit.setEnabled(use_vertex)

            if use_vertex:
                fetch_models_button.setToolTip("Vertex AI（サービスアカウントJSON）から利用可能なモデルリストを取得")
            else:
                fetch_models_button.setToolTip("Gemini APIから利用可能なモデルリストを取得")

        auth_mode_combo.currentIndexChanged.connect(_apply_gemini_auth_mode_ui)

        def _browse_vertex_json():
            try:
                from qt_compat.widgets import QFileDialog
                import os
                import shutil
                from config.common import get_dynamic_file_path

                src, _ = QFileDialog.getOpenFileName(self, "サービスアカウントJSONを選択", "", "JSON (*.json)")
                if not src:
                    return

                # 安全のため input/ai/credentials 配下へコピー（gitignore対象）
                dest_rel = "input/ai/credentials/gemini_vertex_service_account.json"
                dest = get_dynamic_file_path(dest_rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(src, dest)
                vertex_json_edit.setText(dest_rel)
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"JSONの取り込みに失敗しました: {e}")

        vertex_json_browse.clicked.connect(_browse_vertex_json)

        # 初期反映
        _apply_gemini_auth_mode_ui()

        toggle_button.clicked.connect(lambda: self._toggle_provider_details('gemini'))
        
        layout.addWidget(group)

    def _get_models_master_key(self, provider: str) -> str:
        """モデルフィルタ用のマスターキー（Geminiはauth_mode別に分離）"""
        if provider != 'gemini':
            return provider
        try:
            widgets = self.provider_widgets.get('gemini', {})
            mode = widgets.get('auth_mode').currentData() if widgets.get('auth_mode') else None
        except Exception:
            mode = None
        mode_key = str(mode or 'api_key')
        return f"{provider}:{mode_key}"
    
    def setup_local_llm_settings(self, layout):
        """ローカルLLM設定"""
        group = QGroupBox("ローカルLLM設定")
        group_layout = QVBoxLayout(group)

        # 折りたたみヘッダ（常に表示）
        header_layout = QHBoxLayout()
        toggle_button = QPushButton("▶")
        toggle_button.setMaximumWidth(24)
        toggle_button.setToolTip("復元")
        header_layout.addWidget(toggle_button)

        enabled_checkbox = QCheckBox("ローカルLLMを有効にする")
        header_layout.addWidget(enabled_checkbox)

        default_model_label = QLabel("デフォルトモデル:")
        header_layout.addWidget(default_model_label)

        default_model_combo = QComboBox()
        default_model_combo.setEditable(True)
        initial_models = ["llama3.1:8b", "gemma2:9b", "deepseek-r1:7b"]
        self._update_default_model_combo(default_model_combo, initial_models, 'local_llm', 'llama3.1:8b')
        header_layout.addWidget(default_model_combo)
        header_layout.addStretch()
        group_layout.addLayout(header_layout)

        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)

        # 設定フォーム（詳細）
        form_layout = QFormLayout()

        # Base URL（ローカルLLMの場合はAPI Keyの代わり）
        base_url_edit = QLineEdit()
        base_url_edit.setText("http://localhost:11434/api/generate")
        base_url_edit.setPlaceholderText("ローカルLLMサーバーのURLを入力...")
        form_layout.addRow("サーバーURL:", base_url_edit)
        
        # 利用可能モデルラベルと更新ボタン + フィルタ
        models_header_layout = QHBoxLayout()
        models_label = QLabel("利用可能モデル:")
        models_header_layout.addWidget(models_label)
        
        # フィルタ入力
        models_filter = QLineEdit()
        models_filter.setPlaceholderText("フィルタ（例: llama3）")
        models_filter.setMaximumWidth(180)
        models_filter.textChanged.connect(lambda _: self._apply_models_filter('local_llm'))
        models_header_layout.addWidget(models_filter)
        
        clear_filter_btn = QPushButton("解除")
        clear_filter_btn.setMaximumWidth(50)
        clear_filter_btn.clicked.connect(lambda: self._clear_models_filter('local_llm'))
        models_header_layout.addWidget(clear_filter_btn)
        
        # モデル更新ボタン
        fetch_models_button = QPushButton("🔄 サーバーから取得")
        fetch_models_button.setToolTip("ローカルLLMサーバー（Ollama等）から利用可能なモデルリストを取得")
        fetch_models_button.setMaximumWidth(140)
        fetch_models_button.clicked.connect(lambda: self.fetch_available_models('local_llm'))
        models_header_layout.addWidget(fetch_models_button)
        models_header_layout.addStretch()
        
        form_layout.addRow(models_header_layout)
        
        # 利用可能モデルをテーブル表示
        models_table = QTableWidget()
        models_table.setColumnCount(3)
        models_table.setHorizontalHeaderLabels(["デフォルト", "モデル名", "料金情報"])
        models_table.horizontalHeader().setStretchLastSection(True)
        models_table.setMaximumHeight(120)
        models_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        models_table.setToolTip("デフォルトにするモデルをラジオボタンで選択")
        
        # 初期モデルリスト
        initial_models = ["llama3.1:8b", "gemma2:9b", "deepseek-r1:7b"]
        self._populate_models_table(models_table, initial_models, 'local_llm', 'llama3.1:8b')
        form_layout.addRow("", models_table)
        
        # 注意事項
        note_label = QLabel("注意: Ollama等のローカルLLMサーバーが必要です。")
        note_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-style: italic;")
        form_layout.addRow("", note_label)

        details_layout.addLayout(form_layout)
        details_widget.setVisible(False)  # デフォルトは縮小
        group_layout.addWidget(details_widget)
        
        # 価格情報表示（ローカルは対象外）
        pricing_note = QLabel("ローカル環境: 料金情報は対象外です")
        pricing_note.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 11px;")
        form_layout.addRow("", pricing_note)

        # ウィジェット参照を保存（ローカルLLMはAPI Keyがない）
        self.provider_widgets['local_llm'] = {
            'enabled': enabled_checkbox,
            'base_url': base_url_edit,
            'default_model': default_model_combo,
            'models_table': models_table,
            'fetch_button': fetch_models_button,
            'filter': models_filter,
            'clear_filter': clear_filter_btn,
            'toggle_button': toggle_button,
            'details_widget': details_widget,
        }

        toggle_button.clicked.connect(lambda: self._toggle_provider_details('local_llm'))
        
        layout.addWidget(group)
    
    def setup_test_section(self, layout):
        """AIテストセクション"""
        group = QGroupBox("AIテスト機能")
        group_layout = QVBoxLayout(group)
        
        # 説明
        info_label = QLabel(
            "現在の設定でAIプロバイダーとの接続および動作をテストできます。\n"
            "テストは保存された設定またはフォーム内容を使用します。"
        )
        info_label.setWordWrap(True)
        group_layout.addWidget(info_label)
        
        # テストプロバイダー選択
        test_form_layout = QFormLayout()
        
        self.test_provider_combo = QComboBox()
        self.test_provider_combo.addItems(["デフォルト", "openai", "gemini", "local_llm"])
        test_form_layout.addRow("テストプロバイダー:", self.test_provider_combo)
        
        self.test_model_combo = QComboBox()
        self.test_model_combo.setEditable(True)
        test_form_layout.addRow("テストモデル:", self.test_model_combo)
        
        # プロバイダー変更時にモデルリストを更新
        self.test_provider_combo.currentTextChanged.connect(self.update_test_models)
        
        group_layout.addLayout(test_form_layout)
        
        # カスタムプロンプト入力
        prompt_label = QLabel("カスタムプロンプト（オプション）:")
        group_layout.addWidget(prompt_label)
        
        self.custom_prompt_edit = QTextEdit()
        self.custom_prompt_edit.setMaximumHeight(80)
        self.custom_prompt_edit.setPlaceholderText("カスタムプロンプトを入力（空の場合は接続テスト用プロンプトを使用）")
        group_layout.addWidget(self.custom_prompt_edit)
        
        # テストボタン
        test_button_layout = QHBoxLayout()
        
        self.connection_test_button = QPushButton("接続テスト")
        self.connection_test_button.clicked.connect(self.run_connection_test)
        test_button_layout.addWidget(self.connection_test_button)
        
        self.prompt_test_button = QPushButton("プロンプトテスト")
        self.prompt_test_button.clicked.connect(self.run_prompt_test)
        test_button_layout.addWidget(self.prompt_test_button)
        
        test_button_layout.addStretch()
        group_layout.addLayout(test_button_layout)
        
        # プログレスバー
        self.test_progress_bar = QProgressBar()
        self.test_progress_bar.setVisible(False)
        group_layout.addWidget(self.test_progress_bar)
        
        # 結果表示エリア
        result_label = QLabel("テスト結果:")
        group_layout.addWidget(result_label)
        
        self.test_result_area = QTextEdit()
        self.test_result_area.setMaximumHeight(200)
        self.test_result_area.setReadOnly(True)
        self.test_result_area.setPlaceholderText("テスト結果がここに表示されます...")
        group_layout.addWidget(self.test_result_area)

        # リクエスト/レスポンス パラメータ表示（プロンプト/応答本文は省略）
        req_label = QLabel("リクエストパラメータ:")
        group_layout.addWidget(req_label)

        self.test_request_params_area = QTextEdit()
        self.test_request_params_area.setMaximumHeight(140)
        self.test_request_params_area.setReadOnly(True)
        self.test_request_params_area.setPlaceholderText("送信されたリクエストパラメータがここに表示されます...")
        group_layout.addWidget(self.test_request_params_area)

        resp_label = QLabel("レスポンスパラメータ:")
        group_layout.addWidget(resp_label)

        self.test_response_params_area = QTextEdit()
        self.test_response_params_area.setMaximumHeight(140)
        self.test_response_params_area.setReadOnly(True)
        self.test_response_params_area.setPlaceholderText("受信したレスポンスパラメータがここに表示されます...")
        group_layout.addWidget(self.test_response_params_area)
        
        layout.addWidget(group)
    
    def setup_buttons(self, layout):
        """ボタンエリア"""
        button_layout = QHBoxLayout()
        
        # 設定テストボタン
        test_button = QPushButton("設定テスト")
        test_button.clicked.connect(self.test_ai_settings)
        button_layout.addWidget(test_button)
        
        # リセットボタン
        reset_button = QPushButton("リセット")
        reset_button.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(reset_button)
        
        button_layout.addStretch()
        
        # 保存ボタン
        save_button = QPushButton("保存")
        save_button.clicked.connect(self.save_settings)
        button_layout.addWidget(save_button)
        
        # 再読み込みボタン
        reload_button = QPushButton("再読み込み")
        reload_button.clicked.connect(self.load_current_settings)
        button_layout.addWidget(reload_button)
        
        layout.addLayout(button_layout)
    
    def load_current_settings(self):
        """現在の設定を読み込み"""
        try:
            config_path = os.path.abspath(self.config_file_path)
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.current_config = json.load(f)
            else:
                # デフォルト設定を読み込み
                self.load_default_settings()
                return
            
            # UI要素に設定を反映
            self.apply_config_to_ui()
            
        except Exception as e:
            logger.error(f"AI設定読み込みエラー: {e}")
            QMessageBox.warning(self, "エラー", f"AI設定の読み込みに失敗しました: {e}")
            self.load_default_settings()
    
    def load_default_settings(self):
        """デフォルト設定を読み込み"""
        try:
            sample_path = os.path.abspath(get_dynamic_file_path("input/ai_config_sample.json"))
            
            if os.path.exists(sample_path):
                with open(sample_path, 'r', encoding='utf-8') as f:
                    self.current_config = json.load(f)
            else:
                # ハードコードされたデフォルト
                self.current_config = self.get_hardcoded_defaults()
            
            self.apply_config_to_ui()
            
        except Exception as e:
            logger.error(f"デフォルト設定読み込みエラー: {e}")
            self.current_config = self.get_hardcoded_defaults()
            self.apply_config_to_ui()
    
    def get_hardcoded_defaults(self):
        """ハードコードされたデフォルト設定"""
        config = {
            "ai_providers": {
                "openai": {
                    "enabled": True,
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
                    "default_model": "gpt-4o-mini"
                },
                "gemini": {
                    "enabled": True,
                    "api_key": "",
                    "base_url": "https://generativelanguage.googleapis.com/v1beta",
                    "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"],
                    "default_model": "gemini-2.0-flash",
                    "auth_mode": "api_key",
                    "vertex_service_account_json": "",
                    "vertex_project_id": "",
                    "vertex_location": "asia-northeast1",
                },
                "local_llm": {
                    "enabled": False,
                    "base_url": "http://localhost:11434/api/generate",
                    "models": ["llama3.1:8b", "gemma3:1b", "gemma3:4b"],
                    "default_model": "llama3.1:8b"
                }
            },
            "default_provider": "gemini",
            "timeout": 30,
            "max_tokens": 1000,
            "temperature": 0.7,
            "request_max_attempts": 3,
        }
        return normalize_ai_config_inplace(config)
    
    def apply_config_to_ui(self):
        """設定をUIに反映"""
        try:
            # 生成パラメータ含めて正規化（旧設定との互換維持）
            normalize_ai_config_inplace(self.current_config)

            # グローバル設定
            if self.default_provider_combo:
                default_provider = self.current_config.get('default_provider', 'gemini')
                index = self.default_provider_combo.findText(default_provider)
                if index >= 0:
                    self.default_provider_combo.setCurrentIndex(index)
            
            if self.timeout_spinbox:
                self.timeout_spinbox.setValue(self.current_config.get('timeout', 30))

            if self.request_max_attempts_spinbox:
                try:
                    v = int(self.current_config.get('request_max_attempts', 3))
                except Exception:
                    v = 3
                if v < 1:
                    v = 1
                if v > 5:
                    v = 5
                self.request_max_attempts_spinbox.setValue(v)

            # 生成パラメータ（テーブル）
            gen_params = self.current_config.get('generation_params', {})
            for key, controls in self._gen_param_controls.items():
                entry = gen_params.get(key, {})
                use_custom = bool(entry.get('use_custom', False))
                controls['use_custom'].setChecked(use_custom)

                value = entry.get('value')
                widget = controls['value']
                if isinstance(widget, QDoubleSpinBox):
                    try:
                        widget.setValue(float(value))
                    except Exception:
                        pass
                elif isinstance(widget, QSpinBox):
                    try:
                        widget.setValue(int(value))
                    except Exception:
                        pass
                else:
                    # Stop sequencesなど: 表示用に整形
                    if isinstance(value, list):
                        widget.setText(', '.join([str(x) for x in value if str(x).strip()]))
                    elif value is None:
                        widget.setText('')
                    else:
                        widget.setText(str(value))
            
            # プロバイダー設定
            providers = self.current_config.get('ai_providers', {})
            
            for provider_name, widgets in self.provider_widgets.items():
                provider_config = providers.get(provider_name, {})
                
                # 有効化状態
                if 'enabled' in widgets:
                    widgets['enabled'].setChecked(provider_config.get('enabled', False))
                
                # API Key
                if 'api_key' in widgets:
                    widgets['api_key'].setText(provider_config.get('api_key', ''))

                # Gemini: auth_mode / Vertex fields
                if provider_name == 'gemini':
                    if 'auth_mode' in widgets:
                        mode = provider_config.get('auth_mode', 'api_key')
                        idx = widgets['auth_mode'].findData(mode)
                        if idx >= 0:
                            widgets['auth_mode'].setCurrentIndex(idx)
                        else:
                            widgets['auth_mode'].setCurrentIndex(widgets['auth_mode'].findData('api_key'))

                    # 認証方式別のモデル情報をUIキャッシュに取り込み（後方互換あり）
                    try:
                        models_by_auth = provider_config.get('models_by_auth')
                        default_by_auth = provider_config.get('default_model_by_auth')
                        if isinstance(models_by_auth, dict) or isinstance(default_by_auth, dict):
                            for k in ('api_key', 'vertex_sa'):
                                entry: Dict[str, Any] = self._gemini_models_by_auth_ui.get(k, {})
                                if isinstance(models_by_auth, dict) and isinstance(models_by_auth.get(k), list):
                                    entry['models'] = list(models_by_auth.get(k) or [])
                                if isinstance(default_by_auth, dict) and isinstance(default_by_auth.get(k), str):
                                    entry['default_model'] = str(default_by_auth.get(k) or '')
                                if entry:
                                    self._gemini_models_by_auth_ui[k] = entry

                        # 旧形式のみの場合はapi_key側に同期
                        if 'api_key' not in self._gemini_models_by_auth_ui:
                            legacy_models = provider_config.get('models')
                            legacy_default = provider_config.get('default_model')
                            if isinstance(legacy_models, list) or isinstance(legacy_default, str):
                                self._gemini_models_by_auth_ui['api_key'] = {
                                    'models': list(legacy_models or []) if isinstance(legacy_models, list) else [],
                                    'default_model': str(legacy_default or '') if isinstance(legacy_default, str) else '',
                                }
                    except Exception:
                        pass

                    if 'vertex_service_account_json' in widgets:
                        widgets['vertex_service_account_json'].setText(provider_config.get('vertex_service_account_json', ''))
                    if 'vertex_project_id' in widgets:
                        widgets['vertex_project_id'].setText(provider_config.get('vertex_project_id', ''))
                    if 'vertex_location' in widgets:
                        widgets['vertex_location'].setText(provider_config.get('vertex_location', 'asia-northeast1'))
                
                # Base URL
                if 'base_url' in widgets:
                    widgets['base_url'].setText(provider_config.get('base_url', ''))
                
                # デフォルトモデル
                if 'default_model' in widgets:
                    if provider_name == 'gemini':
                        try:
                            mode = widgets.get('auth_mode').currentData() if widgets.get('auth_mode') else None
                        except Exception:
                            mode = None
                        mode_key = str(mode or provider_config.get('auth_mode') or 'api_key')
                        default_by_auth = provider_config.get('default_model_by_auth')
                        default_model = ''
                        if isinstance(default_by_auth, dict):
                            default_model = str(default_by_auth.get(mode_key) or '')
                        if not default_model:
                            # UIキャッシュ→旧形式の順でフォールバック
                            default_model = str((self._gemini_models_by_auth_ui.get(mode_key) or {}).get('default_model') or '')
                        if not default_model:
                            default_model = provider_config.get('default_model', '')
                        widgets['default_model'].setCurrentText(default_model)
                    else:
                        default_model = provider_config.get('default_model', '')
                        widgets['default_model'].setCurrentText(default_model)
                
                # モデルリスト（テーブル or 旧テキストエリア）
                if 'models_table' in widgets:
                    # テーブル表示の場合
                    if provider_name == 'gemini':
                        try:
                            mode = widgets.get('auth_mode').currentData() if widgets.get('auth_mode') else None
                        except Exception:
                            mode = None
                        mode_key = str(mode or provider_config.get('auth_mode') or 'api_key')
                        models_by_auth = provider_config.get('models_by_auth')
                        models = []
                        if isinstance(models_by_auth, dict) and isinstance(models_by_auth.get(mode_key), list):
                            models = list(models_by_auth.get(mode_key) or [])
                        elif isinstance((self._gemini_models_by_auth_ui.get(mode_key) or {}).get('models'), list):
                            models = list((self._gemini_models_by_auth_ui.get(mode_key) or {}).get('models') or [])
                        else:
                            models = provider_config.get('models', [])

                        default_by_auth = provider_config.get('default_model_by_auth')
                        default_model = ''
                        if isinstance(default_by_auth, dict):
                            default_model = str(default_by_auth.get(mode_key) or '')
                        if not default_model:
                            default_model = str((self._gemini_models_by_auth_ui.get(mode_key) or {}).get('default_model') or '')
                        if not default_model:
                            default_model = provider_config.get('default_model', '')
                    else:
                        models = provider_config.get('models', [])
                        default_model = provider_config.get('default_model', '')
                    self._populate_models_table(widgets['models_table'], models, provider_name, default_model)
                    # マスターに保持（フィルタ解除で使う）
                    self._models_master[self._get_models_master_key(provider_name)] = list(models)
                elif 'models' in widgets:
                    # 旧方式（テキストエリア）の場合
                    models = provider_config.get('models', [])
                    models_text = ', '.join(models)
                    widgets['models'].setPlainText(models_text)
                    # マスターに保持（フィルタ解除で使う）
                    self._models_master[self._get_models_master_key(provider_name)] = list(models)
            
            # テスト用モデルリストを初期化
            if hasattr(self, 'test_provider_combo'):
                self.update_test_models()
            
        except Exception as e:
            logger.error(f"設定UI反映エラー: {e}")
            QMessageBox.warning(self, "エラー", f"設定のUI反映に失敗しました: {e}")
    
    def collect_ui_settings(self):
        """UIから設定を収集"""
        try:
            config = {
                "ai_providers": {},
                "default_provider": self.default_provider_combo.currentText(),
                "timeout": self.timeout_spinbox.value(),
                "request_max_attempts": self.request_max_attempts_spinbox.value() if self.request_max_attempts_spinbox else 3,
                "generation_params": {}
            }

            # 生成パラメータを収集
            for spec in GENERATION_PARAM_SPECS:
                controls = self._gen_param_controls.get(spec.key)
                if not controls:
                    continue

                use_custom = bool(controls['use_custom'].isChecked())
                widget = controls['value']

                if isinstance(widget, QDoubleSpinBox):
                    value: Any = float(widget.value())
                elif isinstance(widget, QSpinBox):
                    value = int(widget.value())
                else:
                    value = parse_stop_sequences(widget.text())

                config['generation_params'][spec.key] = {
                    'use_custom': use_custom,
                    'value': value
                }

            # 互換性維持: 旧キーを残す（値はgeneration_paramsから同期）
            try:
                config['max_tokens'] = int(config['generation_params']['max_output_tokens']['value'])
            except Exception:
                config['max_tokens'] = 1000
            try:
                config['temperature'] = float(config['generation_params']['temperature']['value'])
            except Exception:
                config['temperature'] = 0.7
            
            # プロバイダー設定を収集
            for provider_name, widgets in self.provider_widgets.items():
                provider_config = {
                    "enabled": widgets['enabled'].isChecked(),
                    "default_model": widgets['default_model'].currentText()
                }
                
                # API Key（ローカルLLMにはない）
                if 'api_key' in widgets:
                    provider_config['api_key'] = widgets['api_key'].text()

                # Gemini: auth_mode / Vertex fields
                if provider_name == 'gemini':
                    if 'auth_mode' in widgets:
                        provider_config['auth_mode'] = widgets['auth_mode'].currentData() or 'api_key'
                    if 'vertex_service_account_json' in widgets:
                        provider_config['vertex_service_account_json'] = widgets['vertex_service_account_json'].text().strip()
                    if 'vertex_project_id' in widgets:
                        provider_config['vertex_project_id'] = widgets['vertex_project_id'].text().strip()
                    if 'vertex_location' in widgets:
                        provider_config['vertex_location'] = widgets['vertex_location'].text().strip() or 'asia-northeast1'
                
                # Base URL
                if 'base_url' in widgets:
                    provider_config['base_url'] = widgets['base_url'].text()
                
                # モデルリスト（テーブル or 旧テキストエリア）
                if 'models_table' in widgets:
                    # テーブル表示の場合：全行からモデル名を取得
                    table = widgets['models_table']
                    models = []
                    for row in range(table.rowCount()):
                        name_item = table.item(row, 1)
                        if name_item:
                            models.append(name_item.text())
                    provider_config['models'] = models
                elif 'models' in widgets:
                    # 旧方式（テキストエリア）の場合
                    models_text = widgets['models'].toPlainText()
                    models = [model.strip() for model in models_text.split(',') if model.strip()]
                    provider_config['models'] = models

                # Gemini: 認証方式別にmodels/default_modelを保存（後方互換で旧キーも維持）
                if provider_name == 'gemini':
                    try:
                        mode_key = str(provider_config.get('auth_mode') or 'api_key')
                    except Exception:
                        mode_key = 'api_key'

                    # 既存設定（ファイルから読み込まれた内容）も極力保持
                    existing = (self.current_config.get('ai_providers', {}).get('gemini', {}) if isinstance(self.current_config, dict) else {})
                    models_by_auth: Dict[str, Any] = {}
                    default_by_auth: Dict[str, Any] = {}

                    try:
                        if isinstance(existing.get('models_by_auth'), dict):
                            models_by_auth.update(existing.get('models_by_auth') or {})
                        if isinstance(existing.get('default_model_by_auth'), dict):
                            default_by_auth.update(existing.get('default_model_by_auth') or {})
                    except Exception:
                        pass

                    # UI切替中に退避した値もマージ
                    try:
                        for k, v in (self._gemini_models_by_auth_ui or {}).items():
                            if not isinstance(v, dict):
                                continue
                            if isinstance(v.get('models'), list):
                                models_by_auth[k] = list(v.get('models') or [])
                            if isinstance(v.get('default_model'), str):
                                default_by_auth[k] = str(v.get('default_model') or '')
                    except Exception:
                        pass

                    # 現在UIに表示されている値で上書き
                    models_by_auth[mode_key] = list(provider_config.get('models') or [])
                    default_by_auth[mode_key] = str(provider_config.get('default_model') or '')

                    provider_config['models_by_auth'] = models_by_auth
                    provider_config['default_model_by_auth'] = default_by_auth

                    # 旧キーは「現在のauth_modeの値」に同期しておく（実行時互換）
                    provider_config['models'] = list(models_by_auth.get(mode_key) or [])
                    provider_config['default_model'] = str(default_by_auth.get(mode_key) or '')
                
                # ローカルLLMの注記
                if provider_name == 'local_llm':
                    provider_config['note'] = "Ollama等のローカルLLMサーバーが必要です。"
                
                config['ai_providers'][provider_name] = provider_config
            
            return config
            
        except Exception as e:
            logger.error(f"UI設定収集エラー: {e}")
            return None
    
    def save_settings(self):
        """設定を保存"""
        try:
            config = self.collect_ui_settings()
            if config is None:
                return
            
            config_path = os.path.abspath(self.config_file_path)
            
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            # JSON形式で保存
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self.current_config = config
            self.settings_changed.emit()
            
            QMessageBox.information(self, "保存完了", "AI設定が正常に保存されました。")
            
        except Exception as e:
            logger.error(f"AI設定保存エラー: {e}")
            QMessageBox.critical(self, "エラー", f"AI設定の保存に失敗しました: {e}")
    
    def reset_to_defaults(self):
        """デフォルト設定にリセット"""
        reply = QMessageBox.question(
            self, "設定リセット", 
            "AI設定をデフォルトにリセットしますか？\n未保存の変更は失われます。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.load_default_settings()
    
    def fetch_available_models(self, provider):
        """APIから利用可能なモデルリストを取得（非同期・多重実行防止）"""
        try:
            # プロバイダーの設定を取得
            provider_widgets = self.provider_widgets.get(provider)
            if not provider_widgets:
                QMessageBox.warning(self, "エラー", f"プロバイダー '{provider}' の設定が見つかりません。")
                return
            # 多重実行防止
            if provider in self._fetch_inflight:
                QMessageBox.information(self, "取得中", f"{provider.upper()} のモデル取得は進行中です。完了をお待ちください。")
                return

            # Gemini(Vertex) は Vertex SA で取得可能（Bearer）
            gemini_mode = None
            if provider == 'gemini':
                try:
                    gemini_mode = provider_widgets.get('auth_mode').currentData() if provider_widgets.get('auth_mode') else None
                except Exception:
                    gemini_mode = None

            # API Key確認（ローカルLLM以外）
            # - GeminiはAPIキー未設定でも公式ドキュメント解析で候補取得できるため必須にしない
            # - Gemini Vertex SA は当然不要
            if provider != 'local_llm' and provider != 'gemini' and not (provider == 'gemini' and str(gemini_mode or 'api_key') == 'vertex_sa'):
                api_key_edit = provider_widgets.get('api_key')
                if api_key_edit and not api_key_edit.text().strip():
                    QMessageBox.warning(self, "API Key未設定", f"{provider.upper()} API Keyが設定されていません。\nAPI Keyを入力してから再試行してください。")
                    return

            # UI値を読み出し（スレッドに渡す）
            params: Dict[str, Any] = {}
            if provider != 'local_llm':
                params['api_key'] = provider_widgets.get('api_key').text().strip() if provider_widgets.get('api_key') else ''
            params['base_url'] = provider_widgets.get('base_url').text().strip() if provider_widgets.get('base_url') else ''

            if provider == 'gemini' and str(gemini_mode or 'api_key') == 'vertex_sa':
                params['auth_mode'] = 'vertex_sa'
                params['vertex_service_account_json'] = provider_widgets.get('vertex_service_account_json').text().strip() if provider_widgets.get('vertex_service_account_json') else ''
                params['vertex_project_id'] = provider_widgets.get('vertex_project_id').text().strip() if provider_widgets.get('vertex_project_id') else ''
                params['vertex_location'] = provider_widgets.get('vertex_location').text().strip() if provider_widgets.get('vertex_location') else ''

            # 進捗表示
            progress = QMessageBox(self)
            progress.setWindowTitle("モデル取得中")
            progress.setText("ローカルLLMサーバーからモデルリストを取得しています..." if provider == 'local_llm' else f"{provider.upper()} APIからモデルリストを取得しています...")
            progress.setStandardButtons(QMessageBox.NoButton)
            progress.setModal(False)  # ブロッキング防止
            self._progress_boxes[provider] = progress
            progress.show()

            # ボタン無効化＋進行中登録
            fetch_btn = provider_widgets.get('fetch_button')
            if fetch_btn:
                fetch_btn.setEnabled(False)
            self._fetch_inflight.add(provider)

            # ワーカー起動
            worker = _ModelFetchWorker(provider, params)

            def _on_success(models: List[str]):
                try:
                    # テーブル or 旧テキストエリアに反映
                    if 'models_table' in provider_widgets:
                        # 新方式：テーブル表示
                        table = provider_widgets['models_table']
                        # 既存モデルと結合
                        existing_models = []
                        for row in range(table.rowCount()):
                            name_item = table.item(row, 1)
                            if name_item:
                                existing_models.append(name_item.text())
                        all_models = sorted(set(existing_models + models))
                        
                        # デフォルトモデルを取得
                        default_model_combo = provider_widgets.get('default_model')
                        current_default = default_model_combo.currentText() if default_model_combo else ''
                        if not current_default and all_models:
                            current_default = all_models[0]
                        
                        # テーブル再構築
                        self._populate_models_table(table, all_models, provider, current_default)
                        self._models_master[self._get_models_master_key(provider)] = list(all_models)
                        
                        # デフォルトモデルコンボボックスも更新（料金情報付き）
                        if default_model_combo:
                            self._update_default_model_combo(default_model_combo, all_models, provider, current_default)
                    
                    elif 'models' in provider_widgets:
                        # 旧方式：テキストエリア（後方互換）
                        models_edit = provider_widgets['models']
                        existing = [m.strip() for m in models_edit.toPlainText().split(',') if m.strip()]
                        all_models = sorted(set(existing + models))
                        models_edit.setPlainText(', '.join(all_models))
                        self._models_master[self._get_models_master_key(provider)] = list(all_models)
                    
                    # 価格ラベル更新（旧方式のみ）
                    pricing_label = provider_widgets.get('pricing_label')
                    if pricing_label and provider in ('openai', 'gemini'):
                        pricing = self._fetch_pricing_info(provider)
                        if pricing:
                            matched = []
                            for m in self._models_master.get(provider, []):
                                if m in pricing:
                                    matched.append(f"{m}: {pricing[m]}")
                                if len(matched) >= 3:
                                    break
                            pricing_label.setText(" / ".join(matched) if matched else "公式価格ページをご参照ください")
                        else:
                            pricing_label.setText("価格情報を取得できませんでした（ネットワーク/サイト制限）")
                    
                    QMessageBox.information(self, "モデル取得成功", f"{len(models)}個のモデルを取得しました。\n\n取得したモデル:\n" + "\n".join(f"• {m}" for m in models[:10]) + (f"\n... 他{len(models)-10}個" if len(models) > 10 else ""))
                finally:
                    self._finalize_fetch(provider)

            def _on_failed(error: str):
                try:
                    if provider == 'local_llm':
                        QMessageBox.warning(self, "モデル取得失敗", "ローカルLLMサーバーからモデルリストを取得できませんでした。\n\n• サーバーが起動しているか確認してください\n• サーバーURLが正しいか確認してください")
                    else:
                        QMessageBox.warning(self, "モデル取得失敗", f"{provider.upper()} APIからモデルリストを取得できませんでした。\n\n{error}\nAPI Keyとネットワーク接続を確認してください。")
                finally:
                    self._finalize_fetch(provider)

            worker.success.connect(_on_success)
            worker.failed.connect(_on_failed)
            worker.finished.connect(lambda: self._cleanup_worker(provider))
            self._workers[provider] = worker
            worker.start()

        except Exception as e:
            logger.error(f"モデル取得エラー ({provider}): {e}")
            self._finalize_fetch(provider)  # 例外時も後処理
            QMessageBox.critical(self, "エラー", f"モデル取得中にエラーが発生しました:\n{str(e)}")
    
    def _fetch_models_from_api(self, provider, provider_widgets):
        """実際にAPIからモデルリストを取得（同期）"""
        try:
            from net.http_helpers import proxy_get
            if provider == 'openai':
                api_key = provider_widgets['api_key'].text().strip()
                base_url = provider_widgets['base_url'].text().strip().rstrip('/')
                resp = proxy_get(f"{base_url}/models", headers={'Authorization': f'Bearer {api_key}'}, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get('id') for m in data.get('data', []) if m.get('id') and 'gpt' in m.get('id', '').lower()]
                    return sorted(set(models))
                return []
            if provider == 'gemini':
                api_key = provider_widgets['api_key'].text().strip()
                base_url = provider_widgets['base_url'].text().strip().rstrip('/')
                resp = proxy_get(f"{base_url}/models?key={api_key}", timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    models: List[str] = []
                    for m in data.get('models', []):
                        name = m.get('name', '').replace('models/', '')
                        if name and 'gemini' in name.lower():
                            models.append(name)
                    return sorted(set(models))
                return []
            if provider == 'local_llm':
                base_url = provider_widgets['base_url'].text().strip()
                ollama_base = base_url.replace('/api/generate', '').replace('/v1/chat/completions', '')
                resp = proxy_get(f"{ollama_base}/api/tags", timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get('name') for m in data.get('models', []) if m.get('name')]
                    return sorted(set(models))
                return []
            return []
        except Exception as e:
            logger.error(f"API呼び出しエラー ({provider}): {e}")
            return []

    def _fetch_pricing_info(self, provider: str) -> Dict[str, str]:
        """
        モデルの価格情報を取得（公式ドキュメントとスクレイピング）
        
        参照URL:
        - OpenAI: https://platform.openai.com/docs/pricing
        - Gemini: https://ai.google.dev/gemini-api/docs/pricing?hl=ja
        
        Args:
            provider: プロバイダー名 ('openai', 'gemini', 'local_llm')
        
        Returns:
            モデル名と価格情報のマッピング
        """
        try:
            if provider in self._pricing_cache:
                return self._pricing_cache[provider]
            pricing: Dict[str, str] = {}
            
            # 価格スクレイピングは無効化（デフォルト値を使用）
            # import requests を使う場合もRDEトークンが付与されないようにする
            
            if provider == 'openai':
                # OpenAI公式価格ページからスクレイピング（現在は無効化）
                # スクレイピングを有効化する場合は requests.Session() を使用すること
                """
                try:
                    import requests
                    session = requests.Session()
                    session.verify = False
                    resp = session.get("https://platform.openai.com/docs/pricing", timeout=15)
                    if resp.status_code == 200 and resp.text:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        text = resp.text.lower()
                        logger.debug(f"OpenAI価格ページ取得: {len(text)}文字")
                except Exception as e:
                    logger.debug(f"OpenAI価格スクレイピングエラー: {e}")
                """
                
                # 包括的なデフォルト値（2025年11月時点の公式料金）
                pricing.setdefault('gpt-4o', '$5.00/$15.00 per 1M tokens')
                pricing.setdefault('gpt-4o-2024-11-20', '$2.50/$10.00 per 1M tokens')
                pricing.setdefault('gpt-4o-2024-08-06', '$2.50/$10.00 per 1M tokens')
                pricing.setdefault('gpt-4o-2024-05-13', '$5.00/$15.00 per 1M tokens')
                pricing.setdefault('gpt-4o-mini', '$0.15/$0.60 per 1M tokens')
                pricing.setdefault('gpt-4o-mini-2024-07-18', '$0.15/$0.60 per 1M tokens')
                pricing.setdefault('gpt-3.5-turbo', '$0.50/$1.50 per 1M tokens')
                pricing.setdefault('gpt-3.5-turbo-0125', '$0.50/$1.50 per 1M tokens')
                pricing.setdefault('o1-preview', '$15.00/$60.00 per 1M tokens')
                pricing.setdefault('o1-preview-2024-09-12', '$15.00/$60.00 per 1M tokens')
                pricing.setdefault('o1-mini', '$3.00/$12.00 per 1M tokens')
                pricing.setdefault('o1-mini-2024-09-12', '$3.00/$12.00 per 1M tokens')
                pricing.setdefault('gpt-4-turbo', '$10.00/$30.00 per 1M tokens')
                pricing.setdefault('gpt-4-turbo-2024-04-09', '$10.00/$30.00 per 1M tokens')
                pricing.setdefault('gpt-4', '$30.00/$60.00 per 1M tokens')
                pricing.setdefault('gpt-4-0613', '$30.00/$60.00 per 1M tokens')
                pricing.setdefault('gpt-4-32k', '$60.00/$120.00 per 1M tokens')
                
            elif provider == 'gemini':
                # Google Gemini公式価格ページからスクレイピング（現在は無効化）
                # スクレイピングを有効化する場合は requests.Session() を使用すること
                """
                try:
                    import requests
                    session = requests.Session()
                    session.verify = False
                    resp = session.get("https://ai.google.dev/gemini-api/docs/pricing?hl=ja", timeout=15)
                    if resp.status_code == 200 and resp.text:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        text = resp.text.lower()
                        logger.debug(f"Gemini価格ページ取得: {len(text)}文字")
                except Exception as e:
                    logger.debug(f"Gemini価格スクレイピングエラー: {e}")
                """
                
                # 包括的なデフォルト値（2025年11月時点の公式料金）
                # ※128k context以下の料金（それ以上は段階的に料金が上がる）
                pricing.setdefault('gemini-1.5-pro', '$1.25/$5.00 per 1M tokens (≤128k)')
                pricing.setdefault('gemini-1.5-pro-latest', '$1.25/$5.00 per 1M tokens (≤128k)')
                pricing.setdefault('gemini-1.5-pro-001', '$1.25/$5.00 per 1M tokens (≤128k)')
                pricing.setdefault('gemini-1.5-pro-002', '$1.25/$5.00 per 1M tokens (≤128k)')
                pricing.setdefault('gemini-1.5-flash', '$0.075/$0.30 per 1M tokens (≤128k)')
                pricing.setdefault('gemini-1.5-flash-latest', '$0.075/$0.30 per 1M tokens (≤128k)')
                pricing.setdefault('gemini-1.5-flash-001', '$0.075/$0.30 per 1M tokens (≤128k)')
                pricing.setdefault('gemini-1.5-flash-002', '$0.075/$0.30 per 1M tokens (≤128k)')
                pricing.setdefault('gemini-1.5-flash-8b', '$0.0375/$0.15 per 1M tokens (≤128k)')
                pricing.setdefault('gemini-1.5-flash-8b-latest', '$0.0375/$0.15 per 1M tokens (≤128k)')
                pricing.setdefault('gemini-2.0-flash-exp', '無料（実験版・期限あり）')
                pricing.setdefault('gemini-exp-1206', '無料（実験版・期限あり）')
                pricing.setdefault('gemini-1.0-pro', '$0.50/$1.50 per 1M tokens')
                pricing.setdefault('gemini-1.0-pro-latest', '$0.50/$1.50 per 1M tokens')
                pricing.setdefault('gemini-1.0-pro-001', '$0.50/$1.50 per 1M tokens')
                
            else:
                # ローカルLLMなど、価格情報なし
                pricing = {}
            
            self._pricing_cache[provider] = pricing
            return pricing
        except Exception as e:
            logger.debug(f"価格情報取得エラー({provider}): {e}")
            return {}

    def _populate_models_table(self, table: 'QTableWidget', models: list, provider: str, default_model: str):
        """モデルテーブルにラジオボタン・モデル名・料金・接続テストボタンを表示"""
        try:
            table.setRowCount(0)  # 既存行をクリア
            
            # テーブルを4列に拡張（デフォルト、モデル名、料金、接続テスト）
            if table.columnCount() != 4:
                table.setColumnCount(4)
                table.setHorizontalHeaderLabels(["デフォルト", "モデル名", "料金情報", "接続テスト"])
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
                table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
                table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
            
            # デフォルト選択用のボタングループを作成（プロバイダー毎）
            if not hasattr(self, '_default_button_groups'):
                self._default_button_groups = {}
            if provider not in self._default_button_groups:
                self._default_button_groups[provider] = QButtonGroup(self)
                # ラジオボタンクリック時にデフォルトモデルコンボボックスを更新
                self._default_button_groups[provider].buttonToggled.connect(
                    lambda btn, checked, p=provider: self._on_default_model_changed(p, btn, checked)
                )
            
            button_group = self._default_button_groups[provider]
            
            # 料金情報を取得
            pricing_info = self._fetch_pricing_info(provider)
            
            for i, model_name in enumerate(models):
                table.insertRow(i)
                
                # 1列目: デフォルト選択用ラジオボタン
                radio_btn = QRadioButton()
                radio_btn.setProperty('model_name', model_name)  # モデル名を保持
                if model_name == default_model:
                    radio_btn.setChecked(True)
                button_group.addButton(radio_btn, i)
                
                # ラジオボタンを中央配置するためのウィジェット
                radio_widget = QWidget()
                radio_layout = QHBoxLayout(radio_widget)
                radio_layout.addWidget(radio_btn)
                radio_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                radio_layout.setContentsMargins(0, 0, 0, 0)
                table.setCellWidget(i, 0, radio_widget)
                
                # 2列目: モデル名（latestの場合は実モデル名を表示）
                display_name = self._resolve_model_display_name(model_name, provider)
                name_item = QTableWidgetItem(display_name)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # 編集不可
                name_item.setData(Qt.ItemDataRole.UserRole, model_name)  # 実際のモデル名を保持
                table.setItem(i, 1, name_item)
                
                # 3列目: 料金情報
                pricing_text = pricing_info.get(model_name, "料金情報なし")
                pricing_item = QTableWidgetItem(pricing_text)
                pricing_item.setFlags(pricing_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(i, 2, pricing_item)
                
                # 4列目: 接続テストボタン
                test_btn = QPushButton("🔌 テスト")
                test_btn.setToolTip(f"{model_name}への接続をテスト")
                test_btn.setMaximumWidth(80)
                test_btn.clicked.connect(
                    lambda checked, p=provider, m=model_name, r=i: self._test_model_connection(p, m, r)
                )
                table.setCellWidget(i, 3, test_btn)
            
            # 列幅調整
            table.resizeColumnsToContents()
            
        except Exception as e:
            logger.error(f"モデルテーブル表示エラー ({provider}): {e}")

    def _resolve_model_display_name(self, model_name: str, provider: str) -> str:
        """
        モデル名を表示用に解決（latestの場合は実際のモデル名を取得）
        
        Args:
            model_name: モデル名
            provider: プロバイダー名
            
        Returns:
            表示用モデル名
        """
        if 'latest' not in model_name.lower():
            return model_name
        
        # gemini-latestなどの場合、実際のモデル名を取得
        if provider == 'gemini':
            # gemini-latestは現在gemini-1.5-proを指す
            if model_name == 'gemini-latest':
                return f"{model_name} → gemini-1.5-pro"
            elif model_name == 'gemini-1.5-pro-latest':
                return f"{model_name} → gemini-1.5-pro-002"
            elif model_name == 'gemini-1.5-flash-latest':
                return f"{model_name} → gemini-1.5-flash-002"
            elif model_name == 'gemini-1.5-flash-8b-latest':
                return f"{model_name} → gemini-1.5-flash-8b-001"
            elif model_name == 'gemini-1.0-pro-latest':
                return f"{model_name} → gemini-1.0-pro-001"
        
        return model_name
    
    def _update_default_model_combo(self, combo: 'QComboBox', models: list, provider: str, current_default: str):
        """
        デフォルトモデルコンボボックスを更新（料金情報付き）
        
        Args:
            combo: 更新するコンボボックス
            models: モデルリスト
            provider: プロバイダー名
            current_default: 現在のデフォルトモデル
        """
        try:
            combo.clear()
            pricing_info = self._fetch_pricing_info(provider)
            
            for model in models:
                pricing = pricing_info.get(model, "")
                if pricing and pricing != "料金情報なし":
                    display_text = f"{model} ({pricing})"
                else:
                    display_text = model
                
                combo.addItem(display_text, model)  # UserDataに実際のモデル名を保存
            
            # 現在のデフォルトを選択
            if current_default:
                for i in range(combo.count()):
                    if combo.itemData(i) == current_default:
                        combo.setCurrentIndex(i)
                        break
                else:
                    # 見つからない場合はテキストで設定
                    combo.setCurrentText(current_default)
                    
        except Exception as e:
            logger.error(f"デフォルトモデルコンボボックス更新エラー ({provider}): {e}")
            # フォールバック: シンプルに設定
            combo.clear()
            combo.addItems(models)
            if current_default in models:
                combo.setCurrentText(current_default)
    
    def _test_model_connection(self, provider: str, model_name: str, row_index: int):
        """
        指定されたモデルへの接続をテスト
        
        Args:
            provider: プロバイダー名
            model_name: テストするモデル名
            row_index: テーブルの行インデックス
        """
        try:
            logger.info(f"モデル接続テスト開始: {provider}/{model_name}")
            
            # プロバイダーウィジェットを取得
            provider_widgets = self.provider_widgets.get(provider)
            if not provider_widgets:
                raise ValueError(f"プロバイダー設定が見つかりません: {provider}")
            
            # 有効化状態を確認
            enabled_checkbox = provider_widgets.get('enabled')
            if not enabled_checkbox or not enabled_checkbox.isChecked():
                QMessageBox.warning(
                    self,
                    "接続テスト",
                    f"{provider}が有効化されていません。\n設定を確認してください。"
                )
                return
            
            # プロバイダーごとのテスト実行
            if provider == 'openai':
                self._test_openai_connection(model_name, provider_widgets)
            elif provider == 'gemini':
                self._test_gemini_connection(model_name, provider_widgets)
            elif provider == 'local_llm':
                self._test_local_llm_connection(model_name, provider_widgets)
            else:
                raise ValueError(f"未対応のプロバイダー: {provider}")
            
            logger.info(f"モデル接続テスト完了: {provider}/{model_name}")
            
        except Exception as e:
            logger.error(f"モデル接続テストエラー ({provider}/{model_name}): {e}")
            QMessageBox.warning(
                self,
                "接続テストエラー",
                f"接続テストに失敗しました:\n{str(e)}"
            )
    
    def _test_openai_connection(self, model_name: str, provider_widgets: dict):
        """OpenAIモデルの接続テスト"""
        import json
        from net.session_manager import create_new_proxy_session
        
        api_key = provider_widgets['api_key'].text().strip()
        base_url = provider_widgets['base_url'].text().strip()
        
        if not api_key:
            raise ValueError("APIキーが設定されていません")
        
        # 新しいセッションを作成（RDEトークン付与を回避、ただしSSL検証はネットワーク設定に従う）
        session = create_new_proxy_session()
        
        # テストリクエスト（modelsリストを取得して確認）
        url = f"{base_url}/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        response = session.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            models = data.get('data', [])
            
            # 指定モデルが存在するか確認
            model_found = any(m.get('id') == model_name for m in models)
            
            if model_found:
                model_info = next((m for m in models if m.get('id') == model_name), {})
                QMessageBox.information(
                    self,
                    "接続テスト成功",
                    f"✅ {model_name} への接続に成功しました。\n\n"
                    f"モデルID: {model_info.get('id', 'N/A')}\n"
                    f"所有者: {model_info.get('owned_by', 'N/A')}"
                )
            else:
                available_models = [m.get('id', '') for m in models[:10]]
                QMessageBox.warning(
                    self,
                    "モデル未検出",
                    f"API接続は成功しましたが、{model_name} が見つかりません。\n\n"
                    f"利用可能なモデル（一部）:\n" + "\n".join(available_models)
                )
        else:
            raise ValueError(f"API応答エラー (HTTP {response.status_code}): {response.text}")
    
    def _test_gemini_connection(self, model_name: str, provider_widgets: dict):
        """Geminiモデルの接続テスト"""
        # Vertex SA / API key の両対応
        mode = None
        try:
            mode = provider_widgets.get('auth_mode').currentData() if provider_widgets.get('auth_mode') else None
        except Exception:
            mode = None

        if str(mode or 'api_key') == 'vertex_sa':
            # 実際の推論(generateContent)で疎通確認
            from classes.ai.core.ai_manager import AIManager

            mgr = AIManager()
            mgr.config.setdefault('ai_providers', {}).setdefault('gemini', {})
            mgr.config['ai_providers']['gemini'].update(
                {
                    'enabled': True,
                    'auth_mode': 'vertex_sa',
                    'vertex_service_account_json': provider_widgets.get('vertex_service_account_json').text().strip() if provider_widgets.get('vertex_service_account_json') else '',
                    'vertex_project_id': provider_widgets.get('vertex_project_id').text().strip() if provider_widgets.get('vertex_project_id') else '',
                    'vertex_location': provider_widgets.get('vertex_location').text().strip() if provider_widgets.get('vertex_location') else '',
                    'api_key': '',
                }
            )
            mgr.config['timeout'] = 15

            res = mgr.send_prompt('ping', 'gemini', self._resolve_model_display_name(model_name, 'gemini'))
            if isinstance(res, dict) and res.get('success') is True:
                QMessageBox.information(
                    self,
                    "接続テスト成功",
                    f"✅ {model_name} への接続に成功しました。\n\n"
                    f"認証方式: Vertex AI（サービスアカウントJSON）\n"
                    f"モデル: {res.get('model', model_name)}\n"
                    f"応答時間: {res.get('response_time', 'N/A')}"
                )
                return
            raise ValueError(str(res.get('error') if isinstance(res, dict) else res))

        # API key モード: 設定の base_url を利用（既定は v1）
        from net.session_manager import create_new_proxy_session

        api_key = provider_widgets['api_key'].text().strip()
        if not api_key:
            raise ValueError("APIキーが設定されていません")

        base_url = ''
        try:
            base_url = provider_widgets.get('base_url').text().strip() if provider_widgets.get('base_url') else ''
        except Exception:
            base_url = ''
        if not base_url:
            base_url = 'https://generativelanguage.googleapis.com/v1'
        base_url = base_url.rstrip('/')

        # 新しいセッションを作成（RDEトークン付与を回避、ただしSSL検証はネットワーク設定に従う）
        session = create_new_proxy_session()

        # gemini-latestなどの解決
        resolved_name = self._resolve_model_display_name(model_name, 'gemini')

        # テストリクエスト（modelsエンドポイント）
        url = f"{base_url}/models/{resolved_name}?key={api_key}"
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            QMessageBox.information(
                self,
                "接続テスト成功",
                f"✅ {model_name} への接続に成功しました。\n\n"
                f"モデル名: {data.get('displayName', 'N/A')}\n"
                f"説明: {str(data.get('description', 'N/A'))[:50]}..."
            )
            return

        # v1beta固定等で404になった場合のフォールバック
        try:
            text_lower = (response.text or '').lower()
        except Exception:
            text_lower = ''
        if response.status_code == 404 and base_url.endswith('/v1beta') and 'api version v1beta' in text_lower:
            alt_base = base_url[:-len('/v1beta')] + '/v1'
            alt_url = f"{alt_base}/models/{resolved_name}?key={api_key}"
            alt_resp = session.get(alt_url, timeout=10)
            if alt_resp.status_code == 200:
                data = alt_resp.json()
                QMessageBox.information(
                    self,
                    "接続テスト成功",
                    f"✅ {model_name} への接続に成功しました。\n\n"
                    f"(自動フォールバック: v1beta → v1)\n"
                    f"モデル名: {data.get('displayName', 'N/A')}"
                )
                return
            raise ValueError(f"API応答エラー (HTTP {alt_resp.status_code}): {alt_resp.text}")

        raise ValueError(f"API応答エラー (HTTP {response.status_code}): {response.text}")
    
    def _test_local_llm_connection(self, model_name: str, provider_widgets: dict):
        """ローカルLLMモデルの接続テスト"""
        import json
        from net.session_manager import create_new_proxy_session
        
        base_url = provider_widgets['base_url'].text().strip()
        
        if not base_url:
            raise ValueError("サーバーURLが設定されていません")
        
        # 新しいセッションを作成（RDEトークン付与を回避、ただしSSL検証はネットワーク設定に従う）
        session = create_new_proxy_session()
        
        # Ollama形式のテスト（/api/tagsエンドポイント）
        server_base = base_url.rsplit('/api/', 1)[0]
        test_url = f"{server_base}/api/tags"
        
        response = session.get(test_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            model_found = any(m.get('name') == model_name for m in models)
            
            if model_found:
                QMessageBox.information(
                    self,
                    "接続テスト成功",
                    f"✅ {model_name} への接続に成功しました。\n\n"
                    f"サーバー: {server_base}\n"
                    f"利用可能モデル数: {len(models)}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "モデル未検出",
                    f"サーバー接続は成功しましたが、{model_name} が見つかりません。\n\n"
                    f"利用可能なモデル:\n" + "\n".join(m.get('name', '') for m in models[:5])
                )
        else:
            raise ValueError(f"サーバー応答エラー (HTTP {response.status_code}): {response.text}")

    def _on_default_model_changed(self, provider: str, button: 'QRadioButton', checked: bool):
        """デフォルトモデルラジオボタン変更時の処理（料金情報も更新）"""
        if not checked:
            return
        try:
            model_name = button.property('model_name')
            if model_name and provider in self.provider_widgets:
                combo = self.provider_widgets[provider].get('default_model')
                if combo:
                    # 料金情報を取得
                    pricing_info = self._fetch_pricing_info(provider)
                    pricing = pricing_info.get(model_name, "")
                    
                    # コンボボックスのテキストを更新（モデル名 + 料金）
                    if pricing and pricing != "料金情報なし":
                        display_text = f"{model_name} ({pricing})"
                    else:
                        display_text = model_name
                    
                    # 既存のアイテムを探して選択、なければ追加
                    index = combo.findText(model_name)
                    if index >= 0:
                        combo.setCurrentIndex(index)
                    else:
                        combo.setCurrentText(display_text)
                    
        except Exception as e:
            logger.debug(f"デフォルトモデル変更エラー ({provider}): {e}")

    def _apply_models_filter(self, provider: str):
        """モデルリストをフィルタ（テーブル or テキストエリア対応）"""
        try:
            widgets = self.provider_widgets.get(provider, {})
            filter_edit = widgets.get('filter')
            if not filter_edit:
                return
            
            keyword = filter_edit.text().strip().lower()
            
            # テーブル表示の場合
            if 'models_table' in widgets:
                table = widgets['models_table']
                for row in range(table.rowCount()):
                    name_item = table.item(row, 1)
                    if name_item:
                        model_name = name_item.text().lower()
                        # キーワードが空 or 部分一致する場合は表示、それ以外は非表示
                        should_show = (not keyword) or (keyword in model_name)
                        table.setRowHidden(row, not should_show)
            
            # 旧テキストエリアの場合（後方互換）
            elif 'models' in widgets:
                models_edit = widgets['models']
                # マスターから生成（なければ現在値を基準に）
                master = self._models_master.get(self._get_models_master_key(provider))
                if not master:
                    current_text = models_edit.toPlainText()
                    master = [m.strip() for m in current_text.split(',') if m.strip()]
                    self._models_master[self._get_models_master_key(provider)] = list(master)
                
                if keyword:
                    filtered = [m for m in master if keyword in m.lower()]
                else:
                    filtered = master
                filtered = sorted(set(filtered), key=lambda x: x.lower())
                models_edit.setPlainText(', '.join(filtered))
        
        except Exception as e:
            logger.debug(f"モデルフィルタ適用エラー({provider}): {e}")

    def _clear_models_filter(self, provider: str):
        """フィルタ解除し、マスターを表示（テーブル or テキストエリア対応）"""
        try:
            widgets = self.provider_widgets.get(provider, {})
            filter_edit = widgets.get('filter')
            
            if filter_edit:
                filter_edit.setText('')
            
            # テーブル表示の場合
            if 'models_table' in widgets:
                table = widgets['models_table']
                # 全行を表示
                for row in range(table.rowCount()):
                    table.setRowHidden(row, False)
            
            # 旧テキストエリアの場合（後方互換）
            elif 'models' in widgets:
                models_edit = widgets['models']
                master = self._models_master.get(self._get_models_master_key(provider), [])
                models_edit.setPlainText(', '.join(master))
        
        except Exception as e:
            logger.debug(f"モデルフィルタ解除エラー({provider}): {e}")
    
    def test_ai_settings(self):
        """AI設定をテスト"""
        # 簡単な設定検証
        config = self.collect_ui_settings()
        if config is None:
            QMessageBox.warning(self, "エラー", "設定の収集に失敗しました。")
            return
        
        # 有効なプロバイダーをチェック
        enabled_providers = []
        for name, provider in config['ai_providers'].items():
            if provider.get('enabled', False):
                enabled_providers.append(name)
        
        if not enabled_providers:
            QMessageBox.warning(self, "設定エラー", "有効なプロバイダーが設定されていません。")
            return
        
        # 基本的な設定検証
        issues = []
        
        for name in enabled_providers:
            provider = config['ai_providers'][name]
            
            # API Key / Vertex JSON チェック
            if name == 'gemini' and str(provider.get('auth_mode', 'api_key')) == 'vertex_sa':
                if not str(provider.get('vertex_service_account_json', '')).strip():
                    issues.append("gemini: サービスアカウントJSONが設定されていません")
            elif name != 'local_llm' and not provider.get('api_key', '').strip():
                issues.append(f"{name}: API Keyが設定されていません")
            
            # Base URLチェック（Vertexモードのgeminiは不要）
            if not (name == 'gemini' and str(provider.get('auth_mode', 'api_key')) == 'vertex_sa'):
                if not provider.get('base_url', '').strip():
                    issues.append(f"{name}: Base URLが設定されていません")
            
            # モデルチェック
            if not provider.get('models') or len(provider.get('models', [])) == 0:
                issues.append(f"{name}: 利用可能モデルが設定されていません")
        
        # 結果表示
        if issues:
            message = "設定に以下の問題があります:\n\n" + "\n".join(f"• {issue}" for issue in issues)
            QMessageBox.warning(self, "設定検証", message)
        else:
            message = f"設定検証が完了しました。\n\n有効なプロバイダー: {', '.join(enabled_providers)}"
            QMessageBox.information(self, "設定検証", message)
    
    def update_test_models(self):
        """テスト用モデルリストを更新"""
        try:
            provider = self.test_provider_combo.currentText()
            self.test_model_combo.clear()
            
            if provider == "デフォルト":
                # デフォルトプロバイダーのデフォルトモデルを設定
                default_provider = self.default_provider_combo.currentText()
                if default_provider in self.provider_widgets:
                    default_model = self.provider_widgets[default_provider]['default_model'].currentText()
                    self.test_model_combo.addItem(f"{default_model} (デフォルト)")
                    self.test_model_combo.setCurrentText(f"{default_model} (デフォルト)")
            elif provider in self.provider_widgets:
                # プロバイダー固有のモデルリストを設定
                widgets = self.provider_widgets[provider]
                models = []
                
                # テーブル表示の場合
                if 'models_table' in widgets:
                    table = widgets['models_table']
                    for row in range(table.rowCount()):
                        name_item = table.item(row, 1)
                        if name_item:
                            models.append(name_item.text())
                # 旧方式（テキストエリア）の場合
                elif 'models' in widgets:
                    models_text = widgets['models'].toPlainText()
                    models = [model.strip() for model in models_text.split(',') if model.strip()]
                
                if models:
                    self.test_model_combo.addItems(models)
                    
                    # デフォルトモデルを選択
                    if 'default_model' in widgets:
                        default_model = widgets['default_model'].currentText()
                        index = self.test_model_combo.findText(default_model)
                        if index >= 0:
                            self.test_model_combo.setCurrentIndex(index)
            
        except Exception as e:
            logger.error(f"テストモデルリスト更新エラー: {e}")
    
    def get_test_config(self):
        """テスト用設定を取得"""
        try:
            # 現在のフォーム内容から設定を収集
            current_config = self.collect_ui_settings()
            if current_config is None:
                # フォールバック：ファイルから読み込み
                self.load_current_settings()
                current_config = self.current_config
            
            return current_config
            
        except Exception as e:
            logger.error(f"テスト設定取得エラー: {e}")
            return None
    
    def get_test_provider_and_model(self):
        """テスト用プロバイダーとモデルを取得"""
        provider = self.test_provider_combo.currentText()
        model = self.test_model_combo.currentText()
        
        if provider == "デフォルト":
            config = self.get_test_config()
            if config:
                provider = config.get('default_provider', 'gemini')
                providers = config.get('ai_providers', {})
                if provider in providers:
                    model = providers[provider].get('default_model', '')
        
        # "モデル名 (デフォルト)" の形式から実際のモデル名を抽出
        if " (デフォルト)" in model:
            model = model.replace(" (デフォルト)", "")
        
        return provider, model
    
    def run_connection_test(self):
        """接続テストを実行"""
        try:
            provider, model = self.get_test_provider_and_model()
            if not provider or not model:
                QMessageBox.warning(self, "テストエラー", "プロバイダーまたはモデルが選択されていません。")
                return
            self.show_test_progress("接続テスト実行中...")
            test_prompt = "Hello, this is a connection test. Please respond with a simple greeting."
            self.execute_ai_test(provider, model, test_prompt, "接続テスト")
        except Exception as e:
            self.hide_test_progress()
            logger.error(f"接続テストエラー: {e}")
            QMessageBox.critical(self, "エラー", f"接続テストでエラーが発生しました: {e}")
    
    def run_prompt_test(self):
        """プロンプトテストを実行"""
        try:
            provider, model = self.get_test_provider_and_model()
            
            if not provider or not model:
                QMessageBox.warning(self, "テストエラー", "プロバイダーまたはモデルが選択されていません。")
                return
            
            # カスタムプロンプトまたはデフォルトプロンプトを使用
            custom_prompt = self.custom_prompt_edit.toPlainText().strip()
            
            if custom_prompt:
                test_prompt = custom_prompt
                test_type = "カスタムプロンプトテスト"
            else:
                # デフォルトテストプロンプト
                test_prompt = (
                    "以下の質問に200文字程度で回答してください。\n\n"
                    "質問: 人工知能の発展が材料科学分野に与える影響について、"
                    "特にデータ解析と新材料発見の観点から簡潔に説明してください。"
                )
                test_type = "デフォルトプロンプトテスト"
            self.show_test_progress("プロンプトテスト実行中...")
            self.execute_ai_test(provider, model, test_prompt, test_type)
        except Exception as e:
            self.hide_test_progress()
            logger.error(f"プロンプトテストエラー: {e}")
            QMessageBox.critical(self, "エラー", f"プロンプトテストでエラーが発生しました: {e}")

    def _finalize_fetch(self, provider: str):
        """取得処理終了時の共通後処理"""
        try:
            # ボタンを元に戻す
            widgets = self.provider_widgets.get(provider, {})
            fetch_btn = widgets.get('fetch_button')
            if fetch_btn:
                fetch_btn.setEnabled(True)
        except Exception:
            pass
        try:
            # プログレスを完全に閉じて削除
            box = self._progress_boxes.pop(provider, None)
            if box:
                try:
                    box.close()
                    box.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
        self._fetch_inflight.discard(provider)

    def _cleanup_worker(self, provider: str):
        """ワーカー参照のクリーンアップ"""
        worker = self._workers.pop(provider, None)
        if worker:
            try:
                worker.deleteLater()
            except Exception:
                pass

    def get_ai_manager(self):
        """AIマネージャーを取得"""
        try:
            # テスト用の設定でAIマネージャーを作成
            config = self.get_test_config()
            if config is None:
                return None
            
            from classes.ai.core.ai_manager import AIManager
            ai_manager = AIManager()
            ai_manager.config = config  # テスト設定を適用
            
            return ai_manager
            
        except Exception as e:
            logger.error(f"AIマネージャー取得エラー: {e}")
            return None
    
    def show_test_progress(self, message):
        """テストプログレス表示"""
        if hasattr(self, 'test_progress_bar'):
            self.test_progress_bar.setVisible(True)
            self.test_progress_bar.setRange(0, 0)  # 無限プログレス
        if hasattr(self, 'connection_test_button'):
            self.connection_test_button.setEnabled(False)
        if hasattr(self, 'prompt_test_button'):
            self.prompt_test_button.setEnabled(False)
        
        # 結果エリアにプログレス表示
        if hasattr(self, 'test_result_area'):
            self.test_result_area.setText(f"🔄 {message}")

        if hasattr(self, 'test_request_params_area'):
            self.test_request_params_area.setText("")
        if hasattr(self, 'test_response_params_area'):
            self.test_response_params_area.setText("")
    
    def hide_test_progress(self):
        """テストプログレス非表示"""
        if hasattr(self, 'test_progress_bar'):
            self.test_progress_bar.setVisible(False)
        if hasattr(self, 'connection_test_button'):
            self.connection_test_button.setEnabled(True)
        if hasattr(self, 'prompt_test_button'):
            self.prompt_test_button.setEnabled(True)
    
    def execute_ai_test(self, provider: str, model: str, prompt: str, test_type: str):
        """AIテストを実行"""
        try:
            import time
            start_time = time.time()
            
            # AIマネージャーを取得
            ai_manager = self.get_ai_manager()
            if not ai_manager:
                self.hide_test_progress()
                self.show_test_result("❌ エラー", "AIマネージャーの初期化に失敗しました。")
                return

            # リクエストパラメータ表示（本文は省略）
            try:
                req_params = self._build_request_params_for_display(ai_manager, provider, model, prompt)
                if hasattr(self, 'test_request_params_area'):
                    self.test_request_params_area.setText(self._format_as_pretty_json(req_params))
            except Exception as e:
                logger.debug(f"リクエストパラメータ表示エラー: {e}")
            
            # プロンプトを実行
            try:
                result = ai_manager.send_prompt(
                    prompt=prompt,
                    provider=provider,
                    model=model
                )
                
                elapsed_time = time.time() - start_time
                
                # レスポンスパラメータ表示（本文は省略）
                try:
                    resp_params = self._build_response_params_for_display(result)
                    if hasattr(self, 'test_response_params_area'):
                        self.test_response_params_area.setText(self._format_as_pretty_json(resp_params))
                except Exception as e:
                    logger.debug(f"レスポンスパラメータ表示エラー: {e}")

                if result and result.get('response'):
                    tokens_used = result.get('tokens_used')
                    response = result['response']
                    result_text = (
                        f"✅ {test_type}成功\n\n"
                        f"📋 テスト情報:\n"
                        f"  • プロバイダー: {provider}\n"
                        f"  • モデル: {model}\n"
                        f"  • 実行時間: {elapsed_time:.2f}秒\n"
                        + (f"  • 使用トークン: {tokens_used}\n" if isinstance(tokens_used, int) else "")
                        + "\n"
                        f"🤖 AI応答:\n{response}"
                    )
                    self.show_test_result(f"✅ {test_type}成功", result_text)
                else:
                    result_text = (
                        f"⚠️ {test_type}失敗\n\n"
                        f"応答が空でした。\n\n"
                        f"📋 テスト情報:\n"
                        f"  • プロバイダー: {provider}\n"
                        f"  • モデル: {model}\n"
                        f"  • 実行時間: {elapsed_time:.2f}秒"
                    )
                    self.show_test_result(f"⚠️ {test_type}失敗", result_text)
            
            except Exception as api_error:
                elapsed_time = time.time() - start_time
                result_text = (
                    f"❌ {test_type}エラー\n\n"
                    f"エラー内容:\n{str(api_error)}\n\n"
                    f"📋 テスト情報:\n"
                    f"  • プロバイダー: {provider}\n"
                    f"  • モデル: {model}\n"
                    f"  • 実行時間: {elapsed_time:.2f}秒\n\n"
                    f"💡 確認項目:\n"
                    f"  • API Keyが正しく設定されているか\n"
                    f"  • ネットワーク接続が正常か\n"
                    f"  • プロバイダーのサービスが稼働中か"
                )
                self.show_test_result(f"❌ {test_type}エラー", result_text)
        
        except Exception as e:
            logger.error(f"AIテスト実行エラー: {e}")
            self.show_test_result("❌ エラー", f"テスト実行中にエラーが発生しました:\n{str(e)}")
        
        finally:
            self.hide_test_progress()
    
    def show_test_result(self, title, content):
        """テスト結果表示"""
        if hasattr(self, 'test_result_area'):
            self.test_result_area.setText(content)
            
            # 結果に応じてスクロール位置を調整
            if "✅" in title:
                # 成功の場合は応答部分まで自動スクロール
                cursor = self.test_result_area.textCursor()
                cursor.movePosition(cursor.MoveOperation.Start)
                if "🤖 AI応答:" in content:
                    ai_response_pos = content.find("🤖 AI応答:")
                    if ai_response_pos >= 0:
                        cursor.setPosition(ai_response_pos)
                        self.test_result_area.setTextCursor(cursor)
            else:
                # エラーの場合は先頭に戻る
                cursor = self.test_result_area.textCursor()
                cursor.movePosition(cursor.MoveOperation.Start)
                self.test_result_area.setTextCursor(cursor)

    def _toggle_provider_details(self, provider: str):
        """プロバイダ設定の折りたたみ状態を切り替え"""
        widgets = self.provider_widgets.get(provider, {})
        details = widgets.get('details_widget')
        if not details:
            return
        collapsed = details.isVisible()
        self._set_provider_collapsed(provider, collapsed)

    def _set_provider_collapsed(self, provider: str, collapsed: bool):
        """折りたたみ状態を設定（collapsed=Trueで詳細を隠す）"""
        widgets = self.provider_widgets.get(provider, {})
        details = widgets.get('details_widget')
        toggle = widgets.get('toggle_button')
        if details:
            details.setVisible(not collapsed)
        if toggle:
            toggle.setText("▶" if collapsed else "▼")
            toggle.setToolTip("復元" if collapsed else "縮小")

    def _format_as_pretty_json(self, obj: Any) -> str:
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return str(obj)

    def _build_request_params_for_display(self, ai_manager: Any, provider: str, model: str, prompt: str) -> Dict[str, Any]:
        """AIテスト表示用のリクエストパラメータを作成（本文は含めない）"""
        cfg = getattr(ai_manager, 'config', {}) or {}

        if provider == 'openai':
            payload = build_openai_chat_completions_payload(prompt=prompt, model=model, config=cfg)
            safe = {k: v for k, v in payload.items() if k != 'messages'}
            safe['messages_count'] = len(payload.get('messages', []) or [])
            return {'provider': provider, 'model': model, 'payload': safe}

        if provider == 'gemini':
            body = build_gemini_generate_content_body(prompt=prompt, model=model, config=cfg, drop_experimental=False)
            safe = {k: v for k, v in body.items() if k != 'contents'}
            safe['contents_count'] = len(body.get('contents', []) or [])
            return {'provider': provider, 'model': model, 'body': safe}

        if provider == 'local_llm':
            providers = (cfg.get('ai_providers') or {})
            base_url = ((providers.get('local_llm') or {}).get('base_url') or '')
            if '/api/generate' in base_url:
                # Ollama等: /api/generate はprompt本文を除外し、optionsのみ表示
                from classes.ai.util.generation_params import selected_generation_params

                selected = selected_generation_params(cfg)
                options: Dict[str, Any] = {}
                if 'temperature' in selected:
                    options['temperature'] = selected['temperature']
                if 'top_p' in selected:
                    options['top_p'] = selected['top_p']
                if 'top_k' in selected:
                    options['top_k'] = selected['top_k']
                if 'max_output_tokens' in selected:
                    options['num_predict'] = selected['max_output_tokens']
                if 'stop_sequences' in selected:
                    options['stop'] = selected['stop_sequences']

                payload = {'model': model, 'stream': False}
                if options:
                    payload['options'] = options
                return {'provider': provider, 'model': model, 'payload': payload}

            # OpenAI互換
            payload = build_openai_chat_completions_payload(prompt=prompt, model=model, config=cfg)
            payload['stream'] = False
            safe = {k: v for k, v in payload.items() if k != 'messages'}
            safe['messages_count'] = len(payload.get('messages', []) or [])
            return {'provider': provider, 'model': model, 'payload': safe}

        return {'provider': provider, 'model': model}

    def _build_response_params_for_display(self, result: Any) -> Dict[str, Any]:
        """AIテスト表示用のレスポンスパラメータを作成（本文は含めない）"""
        if not isinstance(result, dict):
            return {'raw': str(result)}
        return {k: v for k, v in result.items() if k not in ('response', 'content', 'raw_response')}


class _ModelFetchWorker(QThread):
    """モデル取得ワーカー（HTTPはnet.http_helpers使用）"""
    success = Signal(list)
    failed = Signal(str)

    def __init__(self, provider: str, params: Dict[str, Any]):
        super().__init__()
        self.provider = provider
        self.params = params

    def run(self):
        try:
            provider = self.provider
            p = self.params
            models: List[str] = []

            from net.session_manager import create_new_proxy_session

            # 新しいセッションを作成（RDEトークン付与を回避、ただしSSL検証はネットワーク設定に従う）
            session = create_new_proxy_session()

            def _extract_gemini_models_from_text(text: str) -> List[str]:
                try:
                    import re
                    raw = text or ''
                    # 例: gemini-2.0-flash, gemini-1.5-pro-002, gemini-2.0-flash-exp, gemini-1.5-flash-latest
                    # ai.google.dev内のURL断片（gemini-api等）も混ざるので、後段で除外する
                    pattern = re.compile(r"\bgemini-[0-9a-z][0-9a-z\.\-]*\b", re.IGNORECASE)
                    matches = pattern.findall(raw)
                    cleaned: List[str] = []
                    for m in matches:
                        v = m.strip()
                        if not v:
                            continue
                        v = v.replace('models/', '')
                        # 明らかにパス/説明っぽいものは除外
                        if 'gemini-api' in v.lower():
                            continue
                        # 少なくとも数字を含むものだけをモデル候補として扱う
                        if not any(ch.isdigit() for ch in v):
                            continue
                        cleaned.append(v)
                    return sorted(set(cleaned), key=lambda x: x.lower())
                except Exception:
                    return []

            def _fetch_gemini_models_from_official_docs() -> List[str]:
                """APIキー無しでもモデル候補を得るため、公式ドキュメントから抽出する。"""
                urls = [
                    'https://ai.google.dev/gemini-api/docs/models?hl=ja',
                    'https://ai.google.dev/gemini-api/docs/models',
                ]
                last_text = ''
                for url in urls:
                    try:
                        resp = session.get(url, timeout=(5, 20))
                    except Exception:
                        continue
                    if getattr(resp, 'status_code', None) != 200:
                        continue
                    try:
                        last_text = getattr(resp, 'text', '') or ''
                    except Exception:
                        last_text = ''
                    models = _extract_gemini_models_from_text(last_text)
                    if models:
                        return models
                # 抽出に失敗した場合の最小フォールバック
                return [
                    'gemini-2.5-flash',
                    'gemini-2.5-pro',
                    'gemini-2.0-flash',
                    'gemini-1.5-pro',
                    'gemini-1.5-flash',
                    'gemini-1.0-pro',
                ]
            
            if provider == 'openai':
                api_key = p.get('api_key', '')
                base_url = p.get('base_url', '').rstrip('/')
                if not api_key or not base_url:
                    self.failed.emit('API KeyまたはBase URLが未設定です')
                    return
                resp = session.get(
                    f"{base_url}/models",
                    headers={'Authorization': f'Bearer {api_key}'},
                    timeout=(5, 15)
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m['id'] for m in data.get('data', []) if 'gpt' in m.get('id', '').lower()]
                else:
                    self.failed.emit(f"HTTP {resp.status_code}")
                    return
            elif provider == 'gemini':
                if str(p.get('auth_mode') or 'api_key') == 'vertex_sa':
                    sa_path = str(p.get('vertex_service_account_json') or '').strip()
                    project_id = str(p.get('vertex_project_id') or '').strip()
                    location = str(p.get('vertex_location') or '').strip()
                    api_key = str(p.get('api_key') or '').strip()
                    base_url = str(p.get('base_url') or '').strip()
                    if not sa_path:
                        self.failed.emit('サービスアカウントJSONが未設定です')
                        return
                    if not location:
                        self.failed.emit('Vertex Locationが未設定です')
                        return

                    # トークン取得はAIManagerの既存実装を利用
                    from classes.ai.core.ai_manager import AIManager

                    mgr = AIManager()
                    sa = mgr._load_service_account_json(sa_path)
                    if not project_id:
                        try:
                            project_id = str(sa.get('project_id') or '').strip()
                        except Exception:
                            project_id = ''
                    if not project_id:
                        self.failed.emit('Vertex Project IDが未設定です（設定値またはJSONの project_id を確認してください）')
                        return
                    access_token = mgr._get_vertex_access_token(sa)
                    headers = {
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/json',
                    }

                    def _normalize_api_base_url(raw: str) -> str:
                        url = (raw or '').strip().rstrip('/')
                        if not url:
                            url = 'https://generativelanguage.googleapis.com/v1'
                        # v1beta固定だとモデル取得で404になるケースがあるため、一覧取得はv1を優先する
                        if url.endswith('/v1beta'):
                            url = url[:-len('/v1beta')] + '/v1'
                        return url

                    # 方式変更: Vertex側のモデル一覧APIが企業ネットワーク等で失敗するケースがあるため、
                    # 「APIキーで取得できる候補モデル」をVertex generateContentで疎通確認し、OKのみ返す。
                    candidates: List[str] = []

                    if api_key:
                        api_base = _normalize_api_base_url(base_url)
                        resp = session.get(
                            f"{api_base}/models?key={api_key}",
                            timeout=(5, 20),
                        )
                        if resp.status_code == 200:
                            data = resp.json() if hasattr(resp, 'json') else {}
                            for m in (data.get('models') or []) if isinstance(data, dict) else []:
                                if not isinstance(m, dict):
                                    continue
                                name = str(m.get('name') or '').replace('models/', '').strip()
                                if name and 'gemini' in name.lower():
                                    candidates.append(name)
                        else:
                            # APIキー一覧が取れない場合はフォールバック候補に切り替える
                            candidates = []

                    if not candidates:
                        # APIキー無しでも候補を得る（公式ドキュメント解析）
                        candidates = _fetch_gemini_models_from_official_docs()

                    candidates = sorted(set([c for c in candidates if c]))

                    def _build_vertex_host(loc: str) -> str:
                        return 'https://aiplatform.googleapis.com' if loc == 'global' else f"https://{loc}-aiplatform.googleapis.com"

                    def _build_vertex_generate_url(project: str, loc: str, model_id: str) -> str:
                        host = _build_vertex_host(loc)
                        return f"{host}/v1/projects/{project}/locations/{loc}/publishers/google/models/{model_id}:generateContent"

                    def _is_publisher_model_not_found(resp) -> bool:
                        try:
                            if int(getattr(resp, 'status_code', 0) or 0) != 404:
                                return False
                        except Exception:
                            return False
                        try:
                            text = (getattr(resp, 'text', '') or '').lower()
                        except Exception:
                            text = ''
                        return ('publisher model' in text) and ('not found' in text)

                    payload = {
                        'contents': [{'role': 'user', 'parts': [{'text': 'ping'}]}],
                        'generationConfig': {'maxOutputTokens': 8},
                    }

                    ok: List[str] = []
                    last_error = ''

                    for model_id in candidates:
                        # まずは指定location（日本: asia-northeast1 など）で試す
                        tried: List[tuple[str, str]] = []
                        primary_url = _build_vertex_generate_url(project_id, location, model_id)
                        tried.append((location, primary_url))

                        # 企業ネットワーク等でregional hostが不安定な場合に備えてhostのみglobalへ
                        if location != 'global':
                            tried.append((location, 'https://aiplatform.googleapis.com' + primary_url.split(f"https://{location}-aiplatform.googleapis.com", 1)[-1]))

                        # Publisher Model not found の場合、locations/global を1回試す
                        if location != 'global':
                            tried.append(('global', _build_vertex_generate_url(project_id, 'global', model_id)))

                        model_ok = False
                        for loc_used, url in tried:
                            try:
                                resp = session.post(url, headers=headers, json=payload, timeout=(5, 30))
                            except Exception as e:
                                last_error = f"通信エラー at {url}: {e}"
                                continue

                            if resp.status_code == 200:
                                model_ok = True
                                break

                            # 404の文言が異なる場合もあるので、最終エラーは保持
                            last_error = f"HTTP {resp.status_code} at {url}: {getattr(resp, 'text', '')}"

                            # location=globalへの切替は tried に含めているが、明示的に NOT_FOUND 判定もしておく
                            if _is_publisher_model_not_found(resp):
                                continue

                        if model_ok:
                            ok.append(model_id)

                    models = ok

                    if not models:
                        self.failed.emit(last_error or 'Vertexで利用可能なモデルを判定できませんでした')
                        return
                else:
                    api_key = p.get('api_key', '')
                    base_url = (p.get('base_url', '') or 'https://generativelanguage.googleapis.com/v1').rstrip('/')
                    if api_key:
                        resp = session.get(
                            f"{base_url}/models?key={api_key}",
                            timeout=(5, 15)
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            for m in data.get('models', []):
                                name = m.get('name', '').replace('models/', '')
                                if name and 'gemini' in name.lower():
                                    models.append(name)
                        else:
                            # APIキーがあるのに取得に失敗した場合でも、公式ドキュメントへフォールバック
                            models = _fetch_gemini_models_from_official_docs()
                    else:
                        # APIキー無し: 公式ドキュメント解析で候補を提示
                        models = _fetch_gemini_models_from_official_docs()
            elif provider == 'local_llm':
                base_url = p.get('base_url', '')
                if not base_url:
                    self.failed.emit('サーバーURLが未設定です')
                    return
                ollama_base = base_url.replace('/api/generate', '').replace('/v1/chat/completions', '')
                resp = session.get(f"{ollama_base}/api/tags", timeout=(3, 5))
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m.get('name') for m in data.get('models', []) if m.get('name')]
                else:
                    self.failed.emit(f"HTTP {resp.status_code}")
                    return
            else:
                self.failed.emit('未知のプロバイダーです')
                return

            models = sorted(set(models))
            self.success.emit(models)
        except Exception as e:
            self.failed.emit(str(e))


def create_ai_settings_widget(parent=None, use_internal_scroll: bool = True):
    """AI設定ウィジェットを作成"""
    try:
        return AISettingsWidget(parent, use_internal_scroll=use_internal_scroll)
    except Exception as e:
        logger.error(f"AI設定ウィジェット作成エラー: {e}")
        return None


def get_ai_config():
    """AI設定を取得"""
    try:
        config_path = get_dynamic_file_path("input/ai_config.json")
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                normalize_ai_config_inplace(config)
                # 設定ファイルの構造に合わせて正規化
                if 'ai_providers' in config:
                    # 新しい構造: ai_providers -> providers
                    normalized_config = {
                        'default_provider': config.get('default_provider', 'gemini'),
                        'providers': config.get('ai_providers', {}),
                        'timeout': config.get('timeout', 30),
                        # 互換キー（旧呼び出し側向け）
                        'max_tokens': config.get('max_tokens', 1000),
                        'temperature': config.get('temperature', 0.7),
                        # 新キー
                        'generation_params': config.get('generation_params', {})
                    }
                    return normalized_config
                else:
                    # 旧い構造はそのまま返す
                    return config
        else:
            # デフォルト設定を返す
            return {
                'default_provider': 'gemini',
                'providers': {
                    'gemini': {
                        'default_model': 'gemini-2.0-flash'
                    }
                },
                'generation_params': {}
            }
    except Exception as e:
        logger.error(f"AI設定取得エラー: {e}")
        return None