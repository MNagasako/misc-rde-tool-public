"""
データ取得2機能 - ファイルフィルタUI
複合フィルタ条件設定用のUIコンポーネント
"""

import logging
from typing import Dict, List, Any, Optional, TYPE_CHECKING

from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QSpinBox, QCheckBox, QComboBox,
    QGroupBox, QPushButton, QScrollArea, QTextEdit,
    QFrame, QButtonGroup, QRadioButton, QSlider
)
from qt_compat.core import Qt, Signal
from qt_compat.gui import QFont, QIntValidator

logger = logging.getLogger(__name__)

from ..conf.file_filter_config import (
    FILE_TYPES, MEDIA_TYPES, FILE_EXTENSIONS, 
    FILE_SIZE_RANGES, get_default_filter
)
from ..util.file_filter_util import validate_filter_config, get_filter_summary

class FileFilterWidget(QWidget):
    """ファイルフィルタ設定ウィジェット"""
    
    # フィルタ変更通知シグナル（PySide6: dict→objectに変更）
    filterChanged = Signal(object)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.filter_config = get_default_filter()
        self.setup_ui()
        
    def setup_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # スクロールエリア
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(600)
        
        # メインコンテンツ
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # ファイルタイプフィルタ
        content_layout.addWidget(self.create_filetype_group())
        
        # メディアタイプフィルタ
        content_layout.addWidget(self.create_mediatype_group())
        
        # 拡張子フィルタ
        content_layout.addWidget(self.create_extension_group())
        
        # ファイルサイズフィルタ
        content_layout.addWidget(self.create_filesize_group())
        
        # ファイル名パターンフィルタ
        content_layout.addWidget(self.create_filename_group())
        
        # ダウンロード上限設定
        content_layout.addWidget(self.create_download_limit_group())
        
        # フィルタ操作ボタン
        content_layout.addWidget(self.create_action_buttons())
        
        # フィルタ状況表示
        content_layout.addWidget(self.create_status_display())
        
        content_layout.addStretch()
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
    def create_filetype_group(self) -> "QGroupBox":
        """ファイルタイプ選択グループ"""
        group = QGroupBox("ファイルタイプ")
        layout = QVBoxLayout(group)
        
        # 全選択/全解除ボタン
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("全選択")
        select_none_btn = QPushButton("全解除")
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
            checkbox.stateChanged.connect(self.on_filter_changed)
            # デフォルト設定を反映
            if file_type in self.filter_config["file_types"]:
                checkbox.setChecked(True)
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
        select_none_btn = QPushButton("全解除")
        select_all_btn.clicked.connect(self.select_all_mediatypes)
        select_none_btn.clicked.connect(self.select_none_mediatypes)
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(select_none_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # チェックボックス群
        self.mediatype_checkboxes = {}
        for media_type in MEDIA_TYPES:
            checkbox = QCheckBox(media_type)
            checkbox.stateChanged.connect(self.on_filter_changed)
            self.mediatype_checkboxes[media_type] = checkbox
            layout.addWidget(checkbox)
            
        return group
        
    def create_extension_group(self) -> "QGroupBox":
        """拡張子選択グループ"""
        group = QGroupBox("拡張子")
        layout = QVBoxLayout(group)
        
        # 全選択/全解除ボタン
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("全選択")
        select_none_btn = QPushButton("全解除")
        select_all_btn.clicked.connect(self.select_all_extensions)
        select_none_btn.clicked.connect(self.select_none_extensions)
        button_layout.addWidget(select_all_btn)
        button_layout.addWidget(select_none_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # チェックボックス群（2列レイアウト）
        grid_layout = QGridLayout()
        self.extension_checkboxes = {}
        row, col = 0, 0
        for extension in FILE_EXTENSIONS:
            checkbox = QCheckBox(f".{extension}")
            checkbox.stateChanged.connect(self.on_filter_changed)
            self.extension_checkboxes[extension] = checkbox
            grid_layout.addWidget(checkbox, row, col)
            col += 1
            if col >= 2:
                col = 0
                row += 1
                
        layout.addLayout(grid_layout)
        return group
        
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
        help_label.setStyleSheet("color: #666; font-size: 10px;")
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
        apply_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
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
        self.status_text.setStyleSheet("background-color: #f5f5f5; border: 1px solid #ddd;")
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
        enabled = state == Qt.Checked
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
            "extensions": ["png", "jpeg", "tif"]
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

def create_file_filter_widget(parent=None) -> FileFilterWidget:
    """ファイルフィルタウィジェット作成ファクトリ関数"""
    return FileFilterWidget(parent)