"""
データ取得2機能 - ファイルフィルタUI
複合フィルタ条件設定用のUIコンポーネント
"""

import logging
from typing import Dict, List, Any, Optional, TYPE_CHECKING

from qt_compat import QtCore
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QSpinBox, QCheckBox, QComboBox,
    QGroupBox, QPushButton, QScrollArea, QTextEdit,
    QFrame, QButtonGroup, QRadioButton, QSlider
)
from qt_compat.core import Qt, Signal, QTimer
from qt_compat.widgets import QSizePolicy
from qt_compat.gui import QFont, QIntValidator
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

logger = logging.getLogger(__name__)

from ..conf.file_filter_config import (
    FILE_TYPES, MEDIA_TYPES, FILE_EXTENSIONS,
    FILE_SIZE_RANGES, get_default_filter
)
from classes.config.core import supported_formats_service as formats_service
from ..util.file_filter_util import validate_filter_config, get_filter_summary

class FileFilterWidget(QWidget):
    """ファイルフィルタ設定ウィジェット"""
    
    # フィルタ変更通知シグナル（PySide6: dict→objectに変更）
    filterChanged = Signal(object)

    # 候補キャッシュ（プロセス内メモリ）
    _CACHED_EXTS: List[str] = []
    _CACHED_MEDIA: List[str] = []
    # 初期描画のタイミング計測情報
    _last_timing: Dict[str, float] = {}
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.filter_config = get_default_filter()
        self.setup_ui_content()  # 即座に完全なUIを構築
        
        # ThemeManager接続
        from classes.theme.theme_manager import ThemeManager
        theme_manager = ThemeManager.instance()
        theme_manager.theme_changed.connect(self.refresh_theme)
        
    def setup_ui_content(self):
        """UI本体の構築"""
        # 初期化時の再描画を抑制して一括構築
        import time
        logger.info("[FileFilter] UI構築開始")
        t0 = time.perf_counter()
        
        # 全体の更新を完全に停止
        self.setUpdatesEnabled(False)
        
        # レイアウト作成（既存がなければ新規、あれば再利用）
        layout = self.layout()
        if not layout:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(5, 5, 5, 5)
        
        # レイアウトの自動調整を一時無効化
        layout.setSizeConstraint(QVBoxLayout.SetNoConstraint)
        
        # チェックボックス共通スタイル（視認性向上）
        self.checkbox_style = f"""
            QCheckBox {{
                spacing: 5px;
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                font-size: 10pt;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 3px;
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
            }}
            QCheckBox::indicator:hover {{
                border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};
            }}
            QCheckBox::indicator:checked {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
            }}
        """

        # これまで各チェックボックスに同一のスタイルを個別適用していたが、
        # 大量生成時に setStyleSheet が大きなオーバーヘッドになるため、親で一括適用する。
        # （見た目は同一）
        self.setStyleSheet(self.checkbox_style)
        
        # ボタン共通スタイル（視認性向上）
        self.button_style = f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
                border-radius: 4px;
                padding: 5px 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
                border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
            }}
        """
        
        # まずはタブ上部に「現在のフィルタ設定」と「操作ボタン」を配置（常時表示）
        header_status = self.create_status_display()
        layout.addWidget(header_status)
        header_actions = self.create_action_buttons()
        layout.addWidget(header_actions)

        # スクロールエリア（フィルタ設定本体）
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))
        # 高さは後段で安定化処理時に決定する（過度な固定でスクロールが消えないようにする）
        
        # メインコンテンツ
        content_widget = QWidget()
        content_widget.setUpdatesEnabled(False)
        content_layout = QVBoxLayout(content_widget)
        # コンテンツレイアウトも自動調整を無効化
        content_layout.setSizeConstraint(QVBoxLayout.SetNoConstraint)
        # コンテンツ側は高さを固定せず増加を許容（スクロールバー維持のため）
        
        # 候補リスト拡充（キャッシュ優先 → ソース取り込み）
        t_aug_start = time.perf_counter()
        if not FileFilterWidget._CACHED_EXTS or not FileFilterWidget._CACHED_MEDIA:
            exts, media = self._augment_candidates_from_supported_formats()
            FileFilterWidget._CACHED_EXTS = exts
            FileFilterWidget._CACHED_MEDIA = media
        self._ext_candidates = list(FileFilterWidget._CACHED_EXTS)
        self._media_candidates = list(FileFilterWidget._CACHED_MEDIA)
        t_aug_end = time.perf_counter()
        if not self._ext_candidates:
            self._ext_candidates = list(FILE_EXTENSIONS)
        if not self._media_candidates:
            self._media_candidates = list(MEDIA_TYPES)

        # ファイルタイプフィルタ
        content_layout.addWidget(self.create_filetype_group())
        
        # メディアタイプフィルタ
        t_media_start = time.perf_counter()
        content_layout.addWidget(self.create_mediatype_group())
        t_media_end = time.perf_counter()
        
        # 拡張子フィルタ
        t_ext_start = time.perf_counter()
        content_layout.addWidget(self.create_extension_group())
        t_ext_end = time.perf_counter()
        
        # ファイルサイズフィルタ
        content_layout.addWidget(self.create_filesize_group())
        
        # ファイル名パターンフィルタ
        content_layout.addWidget(self.create_filename_group())
        
        # ダウンロード上限設定
        content_layout.addWidget(self.create_download_limit_group())
        
        # 操作ボタン/状況表示はヘッダに移動したためスクロール対象から除外
        
        content_layout.addStretch()
        
        # スクロールエリアへ設定（まだ更新は無効のまま）
        scroll_area.setWidget(content_widget)
        # スクロール領域がウィンドウ高に追従して伸びるようストレッチを付ける
        layout.addWidget(scroll_area, 1)
        self._filter_scroll_area = scroll_area
        
        # レイアウトを確定させる（ジオメトリ計算を完了）
        logger.info("[FileFilter] レイアウト確定開始")
        content_widget.updateGeometry()
        content_layout.activate()  # レイアウト計算を強制実行
        self.updateGeometry()
        layout.activate()
        logger.info("[FileFilter] レイアウト確定完了")
        
        # 全ての構築とレイアウト計算完了後に一度だけ更新を有効化
        content_widget.setUpdatesEnabled(True)
        self.setUpdatesEnabled(True)
        
        # スクロール領域の高さをウインドウに合わせて初期設定
        self._filter_header_status = header_status
        self._filter_header_actions = header_actions
        self._filter_scroll_area = scroll_area
        # スクロールバーは最初から必要に応じて表示（見た目維持のため）
        try:
            self._filter_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        except Exception:
            pass

        # NOTE:
        # ここでスクロールエリアの minimumHeight をタイマー/resizeEvent で調整すると、
        # 表示後に scroll range が再計算され続け、スクロールバーの長さが「じわじわ」変化して見える。
        # レイアウトと sizePolicy に任せて安定させる。
        self._stabilized = True
        self._stabilize_timer = None

        t_end = time.perf_counter()
        logger.info(f"[FileFilter] UI構築完了: {t_end - t0:.3f}秒")
        FileFilterWidget._last_timing = {
            'total_setup_ui_sec': round(t_end - t0, 6),
            'augment_candidates_sec': round(t_aug_end - t_aug_start, 6),
            'build_mediatype_group_sec': round(t_media_end - t_media_start, 6),
            'build_extension_group_sec': round(t_ext_end - t_ext_start, 6),
        }
        
    def setup_ui(self):
        """UI初期化（旧エントリポイント、互換性のため残す）"""
        self.setup_ui_content()

    def resizeEvent(self, event):
        """リサイズ時: スクロール領域の高さはQtに任せる（後追い調整で段階表示に見えるのを防ぐ）"""
        super().resizeEvent(event)

    def _set_scroll_height(self):
        """タブ領域に合わせてスクロールエリア高さを設定"""
        if not hasattr(self, '_filter_scroll_area') or not self._filter_scroll_area:
            return
        header_height = 0
        if hasattr(self, '_filter_header_status') and self._filter_header_status:
            header_height += self._filter_header_status.sizeHint().height()
        if hasattr(self, '_filter_header_actions') and self._filter_header_actions:
            header_height += self._filter_header_actions.sizeHint().height()
        # パディング分を差し引き、ウインドウに合わせる
        available = max(self.height() - header_height - 20, 200)
        # maxHeightまで固定すると起動中のレイアウト確定で段階的に値が変わりやすい。
        # ここでは最低高さのみ確保し、見た目の段階的変化を抑える。
        self._filter_scroll_area.setMinimumHeight(available)

    def _schedule_stabilize_height(self):
        """初期描画時の高さ確定をデバウンス"""
        if getattr(self, '_stabilize_timer', None) is None:
            self._stabilize_timer = QTimer(self)
            self._stabilize_timer.setSingleShot(True)
            self._stabilize_timer.timeout.connect(self._finalize_initial_height)
        # 40msに短縮し初期表示完了を高速化
        self._stabilize_timer.start(40)

    def _finalize_initial_height(self):
        """初回表示の高さを一度だけ確定し、スクロールバーを有効化"""
        try:
            self._set_scroll_height()
        finally:
            self._stabilized = True
        
    def create_filetype_group(self) -> "QGroupBox":
        """ファイルタイプ選択グループ"""
        group = QGroupBox("ファイルタイプ")
        layout = QVBoxLayout(group)
        
        # 全選択/全解除ボタン
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("全選択")
        select_all_btn.setStyleSheet(self.button_style)
        select_none_btn = QPushButton("全解除")
        select_none_btn.setStyleSheet(self.button_style)
        select_all_btn.clicked.connect(self.select_all_filetypes)
        select_none_btn.clicked.connect(self.select_none_filetypes)
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(select_none_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # チェックボックス群
        self.filetype_checkboxes = {}
        for file_type in FILE_TYPES:
            checkbox = QCheckBox(file_type)
            # デフォルト設定を反映
            if file_type in self.filter_config["file_types"]:
                checkbox.setChecked(True)
            checkbox.stateChanged.connect(self.on_filter_changed)
            self.filetype_checkboxes[file_type] = checkbox
            layout.addWidget(checkbox)
            
        return group
        
    def create_mediatype_group(self) -> "QGroupBox":
        """メディアタイプ選択グループ"""
        group = QGroupBox("メディアタイプ")
        layout = QVBoxLayout(group)
        
        # 全選択/全解除ボタン
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("全選択")
        select_all_btn.setStyleSheet(self.button_style)
        select_none_btn = QPushButton("全解除")
        select_none_btn.setStyleSheet(self.button_style)
        select_all_btn.clicked.connect(self.select_all_mediatypes)
        select_none_btn.clicked.connect(self.select_none_mediatypes)
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(select_none_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # チェックボックス群
        self.mediatype_checkboxes = {}
        for media_type in getattr(self, '_media_candidates', MEDIA_TYPES):
            checkbox = QCheckBox(media_type)
            checkbox.stateChanged.connect(self.on_filter_changed)
            self.mediatype_checkboxes[media_type] = checkbox
            layout.addWidget(checkbox)

        # 任意追加UI
        add_layout = QHBoxLayout()
        add_input = QLineEdit()
        add_input.setPlaceholderText("任意のメディアタイプ（例: image/svg+xml）を追加")
        add_btn = QPushButton("追加")
        add_btn.setStyleSheet(self.button_style)
        # 手動更新ボタン（キャッシュ更新→再構築）
        refresh_btn = QPushButton("🔄 更新")
        refresh_btn.setToolTip("対応形式を再取得して一覧を更新")
        refresh_btn.setStyleSheet(self.button_style)
        def _refresh_media():
            exts, media = self._augment_candidates_from_supported_formats()
            FileFilterWidget._CACHED_EXTS = exts
            FileFilterWidget._CACHED_MEDIA = media
            self._rebuild_mediatype_group(layout)
        refresh_btn.clicked.connect(_refresh_media)
        def _add_media_type():
            text = add_input.text().strip()
            if not text:
                return
            if text not in self.mediatype_checkboxes:
                cb = QCheckBox(text)
                cb.setChecked(True)
                cb.stateChanged.connect(self.on_filter_changed)
                self.mediatype_checkboxes[text] = cb
                layout.addWidget(cb)
                self.on_filter_changed()
                add_input.clear()
        add_btn.clicked.connect(_add_media_type)
        add_layout.addWidget(add_input)
        add_layout.addWidget(add_btn)
        add_layout.addWidget(refresh_btn)
        layout.addLayout(add_layout)
            
        return group

    def _rebuild_mediatype_group(self, layout: QVBoxLayout):
        """メディアタイプグループをキャッシュから再構築"""
        try:
            # 既存チェックボックス削除
            for mt, cb in list(getattr(self, 'mediatype_checkboxes', {}).items()):
                cb.setParent(None)
            self.mediatype_checkboxes = {}
            # 新規候補で再追加
            for media_type in FileFilterWidget._CACHED_MEDIA:
                checkbox = QCheckBox(media_type)
                checkbox.stateChanged.connect(self.on_filter_changed)
                self.mediatype_checkboxes[media_type] = checkbox
                layout.addWidget(checkbox)
            self.on_filter_changed()
        except Exception:
            pass
        
    def create_extension_group(self) -> "QGroupBox":
        """拡張子選択グループ"""
        group = QGroupBox("拡張子")
        layout = QVBoxLayout(group)
        
        # 全選択/全解除ボタン
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("全選択")
        select_all_btn.setStyleSheet(self.button_style)
        select_none_btn = QPushButton("全解除")
        select_none_btn.setStyleSheet(self.button_style)
        select_all_btn.clicked.connect(self.select_all_extensions)
        select_none_btn.clicked.connect(self.select_none_extensions)
        # 手動更新ボタン（キャッシュ更新→再構築）
        refresh_btn = QPushButton("🔄 更新")
        refresh_btn.setToolTip("対応形式を再取得して一覧を更新")
        refresh_btn.setStyleSheet(self.button_style)
        def _refresh_exts():
            exts, media = self._augment_candidates_from_supported_formats()
            FileFilterWidget._CACHED_EXTS = exts
            FileFilterWidget._CACHED_MEDIA = media
            self._rebuild_extension_grid(layout)
        refresh_btn.clicked.connect(_refresh_exts)
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(select_none_btn)
        button_layout.addWidget(refresh_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # チェックボックス群（7列レイアウト）をコンテナ内で一括構築
        container = QWidget(group)
        container.setUpdatesEnabled(False)
        grid_layout = QGridLayout(container)
        grid_layout.setHorizontalSpacing(12)
        grid_layout.setVerticalSpacing(6)
        self.extension_checkboxes = {}
        columns = 7
        row, col = 0, 0
        # シグナルを後でまとめて接続するために一時保持
        pending_checkboxes: List[QCheckBox] = []
        for extension in getattr(self, '_ext_candidates', FILE_EXTENSIONS):
            checkbox = QCheckBox(f".{extension}", parent=container)
            self.extension_checkboxes[extension] = checkbox
            grid_layout.addWidget(checkbox, row, col)
            pending_checkboxes.append(checkbox)
            col += 1
            if col >= columns:
                col = 0
                row += 1

        # メタ情報保持
        self._ext_grid_layout = grid_layout
        self._ext_grid_cols = columns
        self._ext_grid_pos = (row, col)
        
        # まとめて接続（描画解放前に一度だけ）
        for cb in pending_checkboxes:
            cb.stateChanged.connect(self.on_filter_changed)
        
        # 一括構築完了後にコンテナを追加して表示
        container.setUpdatesEnabled(True)
        layout.addWidget(container)

        # 任意追加UI
        add_layout = QHBoxLayout()
        add_input = QLineEdit()
        add_input.setPlaceholderText("任意の拡張子を追加（例: svg, raw）")
        add_btn = QPushButton("追加")
        add_btn.setStyleSheet(self.button_style)
        def _add_extension():
            raw = add_input.text().strip().lower()
            if not raw:
                return
            ext = raw.lstrip('.')
            if ext not in self.extension_checkboxes:
                cb = QCheckBox(f".{ext}")
                cb.setChecked(True)
                cb.stateChanged.connect(self.on_filter_changed)
                self.extension_checkboxes[ext] = cb
                # 新規もグリッドに追加（5列で折り返し）
                row, col = getattr(self, '_ext_grid_pos', (0, 0))
                cols = getattr(self, '_ext_grid_cols', 5)
                grid = getattr(self, '_ext_grid_layout', None)
                if grid is not None:
                    grid.addWidget(cb, row, col)
                    col += 1
                    if col >= cols:
                        col = 0
                        row += 1
                    self._ext_grid_pos = (row, col)
                self.on_filter_changed()
                add_input.clear()
        add_btn.clicked.connect(_add_extension)
        add_layout.addWidget(add_input)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)
        return group

    def _rebuild_extension_grid(self, layout: QVBoxLayout):
        """拡張子グリッドをキャッシュから再構築"""
        try:
            # 既存チェックボックス削除
            for ext, cb in list(getattr(self, 'extension_checkboxes', {}).items()):
                cb.setParent(None)
            # 新しいグリッド
            grid_layout = QGridLayout()
            grid_layout.setHorizontalSpacing(12)
            grid_layout.setVerticalSpacing(6)
            self.extension_checkboxes = {}
            columns = getattr(self, '_ext_grid_cols', 7)
            row, col = 0, 0
            for extension in FileFilterWidget._CACHED_EXTS:
                checkbox = QCheckBox(f".{extension}")
                checkbox.stateChanged.connect(self.on_filter_changed)
                self.extension_checkboxes[extension] = checkbox
                grid_layout.addWidget(checkbox, row, col)
                col += 1
                if col >= columns:
                    col = 0
                    row += 1
            self._ext_grid_layout = grid_layout
            self._ext_grid_cols = columns
            self._ext_grid_pos = (row, col)
            # 既存のレイアウト末尾に再追加（旧グリッドの親からは外している）
            layout.addLayout(grid_layout)
            self.on_filter_changed()
        except Exception:
            pass

    @staticmethod
    def get_last_timing() -> Dict[str, float]:
        """直近の初期描画タイミング情報を取得"""
        return dict(FileFilterWidget._last_timing)
        
    def create_filesize_group(self) -> "QGroupBox":
        """ファイルサイズフィルタグループ"""
        group = QGroupBox("ファイルサイズ")
        layout = QVBoxLayout(group)
        
        # サイズ範囲選択（プリセット）
        preset_layout = QHBoxLayout()
        preset_label = QLabel("プリセット:")
        self.size_preset_combo = QComboBox()
        self.size_preset_combo.addItem("制限なし", (0, 0))
        for name, (min_size, max_size) in FILE_SIZE_RANGES.items():
            if max_size == float('inf'):
                label = f"{name.capitalize()} ({min_size//1024}KB以上)"
            else:
                label = f"{name.capitalize()} ({min_size//1024}KB-{max_size//1024}KB)"
            self.size_preset_combo.addItem(label, (min_size, max_size))
        self.size_preset_combo.currentIndexChanged.connect(self.on_size_preset_changed)
        preset_layout.addWidget(preset_label)
        preset_layout.addWidget(self.size_preset_combo)
        preset_layout.addStretch()
        layout.addLayout(preset_layout)
        
        # 詳細設定
        detail_layout = QGridLayout()
        
        # 最小サイズ
        detail_layout.addWidget(QLabel("最小サイズ (bytes):"), 0, 0)
        self.size_min_input = QLineEdit()
        self.size_min_input.setValidator(QIntValidator(0, 999999999))
        self.size_min_input.setText("0")
        self.size_min_input.textChanged.connect(self.on_filter_changed)
        detail_layout.addWidget(self.size_min_input, 0, 1)
        
        # 最大サイズ
        detail_layout.addWidget(QLabel("最大サイズ (bytes):"), 1, 0)
        self.size_max_input = QLineEdit()
        self.size_max_input.setValidator(QIntValidator(0, 999999999))
        self.size_max_input.setPlaceholderText("0 = 制限なし")
        self.size_max_input.textChanged.connect(self.on_filter_changed)
        detail_layout.addWidget(self.size_max_input, 1, 1)
        
        layout.addLayout(detail_layout)
        return group
        
    def create_filename_group(self) -> "QGroupBox":
        """ファイル名パターングループ"""
        group = QGroupBox("ファイル名パターン")
        layout = QVBoxLayout(group)
        
        # パターン入力
        pattern_layout = QHBoxLayout()
        pattern_label = QLabel("パターン:")
        self.filename_pattern_input = QLineEdit()
        self.filename_pattern_input.setPlaceholderText("*を使用可能（例: *.png, test_*, *data*）")
        self.filename_pattern_input.textChanged.connect(self.on_filter_changed)
        pattern_layout.addWidget(pattern_label)
        pattern_layout.addWidget(self.filename_pattern_input)
        layout.addLayout(pattern_layout)
        
        # ヘルプテキスト
        help_label = QLabel("• 完全一致または*でワイルドカード指定\\n• 大文字小文字は区別しません")
        help_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px;")
        layout.addWidget(help_label)
        
        return group
        
    def create_download_limit_group(self) -> "QGroupBox":
        """ダウンロード上限設定グループ"""
        group = QGroupBox("ダウンロード上限")
        layout = QVBoxLayout(group)
        
        # 上限設定
        limit_layout = QHBoxLayout()
        self.limit_checkbox = QCheckBox("ダウンロード数を制限する")
        self.limit_checkbox.stateChanged.connect(self.on_limit_checkbox_changed)
        layout.addWidget(self.limit_checkbox)
        
        limit_input_layout = QHBoxLayout()
        self.limit_spinbox = QSpinBox()
        self.limit_spinbox.setMinimum(1)
        self.limit_spinbox.setMaximum(10000)
        self.limit_spinbox.setValue(100)
        self.limit_spinbox.setEnabled(False)
        self.limit_spinbox.valueChanged.connect(self.on_filter_changed)
        limit_input_layout.addWidget(QLabel("最大:"))
        limit_input_layout.addWidget(self.limit_spinbox)
        limit_input_layout.addWidget(QLabel("件"))
        limit_input_layout.addStretch()
        layout.addLayout(limit_input_layout)
        
        return group
        
    def create_action_buttons(self) -> "QWidget":
        """操作ボタン群"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        # フィルタリセット
        reset_btn = QPushButton("🔄 リセット")
        reset_btn.clicked.connect(self.reset_filter)
        reset_btn.setToolTip("フィルタ設定をデフォルトに戻します")
        layout.addWidget(reset_btn)
        
        # プリセット適用
        preset_btn = QPushButton("📋 プリセット")
        preset_btn.clicked.connect(self.apply_preset_filter)
        preset_btn.setToolTip("よく使用される設定を適用します")
        layout.addWidget(preset_btn)
        
        layout.addStretch()
        
        # フィルタ適用
        apply_btn = QPushButton("✅ フィルタ適用")
        apply_btn.setStyleSheet(f"""
            background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
            color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
            font-weight: bold;
        """)
        apply_btn.clicked.connect(self.apply_filter)
        layout.addWidget(apply_btn)
        
        return widget
        
    def create_status_display(self) -> "QGroupBox":
        """フィルタ状況表示"""
        group = QGroupBox("現在のフィルタ設定")
        layout = QVBoxLayout(group)
        
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(80)
        self.status_text.setStyleSheet(f"""
            background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)};
            border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
        """)
        layout.addWidget(self.status_text)
        
        self.update_status_display()
        return group
        
    def get_filter_config(self) -> Dict[str, Any]:
        """現在のフィルタ設定を取得"""
        config = {}
        
        # ファイルタイプ
        config["file_types"] = [
            file_type for file_type, checkbox in getattr(self, 'filetype_checkboxes', {}).items()
            if checkbox.isChecked()
        ]
        
        # メディアタイプ
        config["media_types"] = [
            media_type for media_type, checkbox in getattr(self, 'mediatype_checkboxes', {}).items()
            if checkbox.isChecked()
        ]
        
        # 拡張子
        config["extensions"] = [
            ext for ext, checkbox in getattr(self, 'extension_checkboxes', {}).items()
            if checkbox.isChecked()
        ]
        
        # ファイルサイズ
        try:
            config["size_min"] = int(self.size_min_input.text()) if hasattr(self, 'size_min_input') and self.size_min_input.text() else 0
        except (ValueError, AttributeError):
            config["size_min"] = 0
            
        try:
            config["size_max"] = int(self.size_max_input.text()) if hasattr(self, 'size_max_input') and self.size_max_input.text() else 0
        except (ValueError, AttributeError):
            config["size_max"] = 0
            
        # ファイル名パターン
        config["filename_pattern"] = self.filename_pattern_input.text().strip() if hasattr(self, 'filename_pattern_input') else ""
        
        # ダウンロード上限
        if hasattr(self, 'limit_checkbox') and hasattr(self, 'limit_spinbox') and self.limit_checkbox.isChecked():
            config["max_download_count"] = self.limit_spinbox.value()
        else:
            config["max_download_count"] = 0
            
        return config
        
    def set_filter_config(self, config: Dict[str, Any]):
        """フィルタ設定を適用"""
        self.filter_config = config.copy()

        # 大量のチェックボックスを切り替える際に stateChanged→on_filter_changed が連発すると遅くなるため、
        # ここでは一時的にシグナル/再描画を抑止して一括反映する。
        self.setUpdatesEnabled(False)
        try:
            def _block_all(flag: bool):
                for cb in getattr(self, 'filetype_checkboxes', {}).values():
                    cb.blockSignals(flag)
                for cb in getattr(self, 'mediatype_checkboxes', {}).values():
                    cb.blockSignals(flag)
                for cb in getattr(self, 'extension_checkboxes', {}).values():
                    cb.blockSignals(flag)
                if hasattr(self, 'size_preset_combo'):
                    self.size_preset_combo.blockSignals(flag)
                if hasattr(self, 'size_min_input'):
                    self.size_min_input.blockSignals(flag)
                if hasattr(self, 'size_max_input'):
                    self.size_max_input.blockSignals(flag)
                if hasattr(self, 'filename_pattern_input'):
                    self.filename_pattern_input.blockSignals(flag)
                if hasattr(self, 'limit_checkbox'):
                    self.limit_checkbox.blockSignals(flag)
                if hasattr(self, 'limit_spinbox'):
                    self.limit_spinbox.blockSignals(flag)

            _block_all(True)
            try:
                # ファイルタイプ
                file_types = config.get("file_types", [])
                for file_type, checkbox in getattr(self, 'filetype_checkboxes', {}).items():
                    checkbox.setChecked(file_type in file_types)

                # メディアタイプ
                media_types = config.get("media_types", [])
                for media_type, checkbox in getattr(self, 'mediatype_checkboxes', {}).items():
                    checkbox.setChecked(media_type in media_types)

                # 拡張子
                extensions = config.get("extensions", [])
                for ext, checkbox in getattr(self, 'extension_checkboxes', {}).items():
                    checkbox.setChecked(ext in extensions)

                # ファイルサイズ
                if hasattr(self, 'size_min_input'):
                    self.size_min_input.setText(str(config.get("size_min", 0)))
                if hasattr(self, 'size_max_input'):
                    self.size_max_input.setText(str(config.get("size_max", 0)))

                # ファイル名パターン
                if hasattr(self, 'filename_pattern_input'):
                    self.filename_pattern_input.setText(config.get("filename_pattern", ""))

                # ダウンロード上限
                max_count = config.get("max_download_count", 0)
                self.limit_checkbox.setChecked(max_count > 0)
                self.limit_spinbox.setEnabled(max_count > 0)
                if max_count > 0:
                    self.limit_spinbox.setValue(max_count)
            finally:
                _block_all(False)
        finally:
            self.setUpdatesEnabled(True)

        self.update_status_display()
        
    # イベントハンドラ
    def on_filter_changed(self):
        """フィルタ変更時"""
        self.filter_config = self.get_filter_config()
        self.update_status_display()
        self.filterChanged.emit(self.filter_config)
        
    def on_size_preset_changed(self, index):
        """サイズプリセット変更時"""
        min_size, max_size = self.size_preset_combo.itemData(index)
        self.size_min_input.setText(str(min_size))
        if max_size == float('inf'):
            self.size_max_input.setText("0")
        else:
            self.size_max_input.setText(str(max_size))
        self.on_filter_changed()
        
    def on_limit_checkbox_changed(self, state):
        """ダウンロード上限チェックボックス変更時"""
        enabled = state == 2  # Qt.CheckState.Checked.value
        self.limit_spinbox.setEnabled(enabled)
        self.on_filter_changed()
        
    def select_all_filetypes(self):
        """全ファイルタイプ選択"""
        for checkbox in self.filetype_checkboxes.values():
            checkbox.setChecked(True)
            
    def select_none_filetypes(self):
        """全ファイルタイプ選択解除"""
        for checkbox in self.filetype_checkboxes.values():
            checkbox.setChecked(False)
            
    def select_all_mediatypes(self):
        """全メディアタイプ選択"""
        for checkbox in self.mediatype_checkboxes.values():
            checkbox.setChecked(True)
            
    def select_none_mediatypes(self):
        """全メディアタイプ選択解除"""
        for checkbox in self.mediatype_checkboxes.values():
            checkbox.setChecked(False)
            
    def select_all_extensions(self):
        """全拡張子選択"""
        for checkbox in self.extension_checkboxes.values():
            checkbox.setChecked(True)
            
    def select_none_extensions(self):
        """全拡張子選択解除"""
        for checkbox in self.extension_checkboxes.values():
            checkbox.setChecked(False)
            
    def reset_filter(self):
        """フィルタリセット"""
        self.set_filter_config(get_default_filter())
        
    def apply_preset_filter(self):
        """プリセットフィルタ適用"""
        # 画像ファイルのみのプリセット例
        preset_config = get_default_filter()
        preset_config.update({
            "file_types": ["MAIN_IMAGE"],
            "media_types": ["image/png", "image/jpeg", "image/tiff"],
            "extensions": ["png", "jpg", "jpeg", "tif"]
        })
        self.set_filter_config(preset_config)
        
    def apply_filter(self):
        """フィルタ適用"""
        config = self.get_filter_config()
        errors = validate_filter_config(config)
        
        if errors:
            # エラー表示（簡易実装）
            error_msg = "\\n".join(errors)
            logger.error(f"フィルタ設定エラー: {error_msg}")
            return
            
        self.filter_config = config
        self.filterChanged.emit(config)
        
    def update_status_display(self):
        """状況表示更新"""
        try:
            from classes.data_fetch2.util.file_filter_util import get_filter_summary
            summary = get_filter_summary(self.filter_config)
            if hasattr(self, 'status_text'):
                self.status_text.setPlainText(summary)
        except ImportError:
            pass
    
    def refresh_theme(self):
        """テーマ切替時の更新処理"""
        try:
            # チェックボックススタイル再生成
            self.checkbox_style = f"""
                QCheckBox {{
                    spacing: 5px;
                    color: {get_color(ThemeKey.TEXT_PRIMARY)};
                    font-size: 10pt;
                }}
                QCheckBox::indicator {{
                    width: 18px;
                    height: 18px;
                    border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                    border-radius: 3px;
                    background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                }}
                QCheckBox::indicator:hover {{
                    border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};
                }}
                QCheckBox::indicator:checked {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                }}
            """

            # 大量のチェックボックスに個別 setStyleSheet をかけると重いため、親で一括適用する。
            self.setStyleSheet(self.checkbox_style)
            
            # ボタンスタイル再生成
            self.button_style = f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                    border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
                    border-radius: 4px;
                    padding: 5px 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
                    border-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                }}
                QPushButton:pressed {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                }}
            """
            
            # 全選択/全解除ボタンにのみスタイル適用（個別スタイルを持つボタンは除外）
            # findChildrenで全ボタンを取得せず、GroupBox内の全選択/全解除ボタンのみ対象
            from qt_compat.widgets import QPushButton, QGroupBox
            for group in self.findChildren(QGroupBox):
                for button in group.findChildren(QPushButton):
                    # "全選択"/"全解除"ボタンのみ更新（他は個別スタイルを保持）
                    if button.text() in ["全選択", "全解除"]:
                        button.setStyleSheet(self.button_style)
            
            # status_textの背景色を更新
            if hasattr(self, 'status_text') and self.status_text:
                self.status_text.setStyleSheet(f"""
                    background-color: {get_color(ThemeKey.INPUT_BACKGROUND_DISABLED)};
                    border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                    color: {get_color(ThemeKey.TEXT_PRIMARY)};
                """)
            
            self.update()
        except Exception as e:
            logger.error(f"FileFilterWidget: テーマ更新エラー: {e}")

    def _augment_candidates_from_supported_formats(self):
        """対応ファイル形式JSONから拡張子候補と対応メディアタイプ候補を拡充し返す。
        取得済みの形式を初期値として採用する。
        戻り値: (extensions: List[str], media_types: List[str])
        """
        try:
            import os, json
            out_path = formats_service.get_default_output_path()
            if not os.path.exists(out_path):
                return (list(FILE_EXTENSIONS), list(MEDIA_TYPES))
            with open(out_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            entries = meta.get("entries") or []
            exts = set(FILE_EXTENSIONS)
            media = set(MEDIA_TYPES)

            # 既知拡張子→MIMEの簡易マップ（不足は任意追加で補完可能）
            mime_map = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "tif": "image/tiff",
                "tiff": "image/tiff",
                "csv": "text/csv",
                "json": "application/json",
                "txt": "text/plain",
                "pdf": "application/pdf",
                "xml": "application/xml",
            }

            for e in entries:
                for ext in (e.get("file_exts") or []):
                    if isinstance(ext, str) and ext:
                        exts.add(ext.lower())
                        mt = mime_map.get(ext.lower())
                        if mt:
                            media.add(mt)

            # 更新反映（順序はアルファベット順に整える）
            return (sorted(exts), sorted(media))
        except Exception as exc:
            logger.warning(f"対応形式候補の取り込みに失敗: {exc}")
            return (list(FILE_EXTENSIONS), list(MEDIA_TYPES))

def create_file_filter_widget(parent=None) -> FileFilterWidget:
    """ファイルフィルタウィジェット作成ファクトリ関数"""
    return FileFilterWidget(parent)