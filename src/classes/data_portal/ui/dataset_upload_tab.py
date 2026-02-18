from __future__ import annotations

"""
データセットJSONアップロードタブ UI

JSONファイルをデータポータルにアップロードする機能を提供
"""

import os
import json
from pathlib import Path
from typing import Tuple, Any, Dict, Set, Optional, TYPE_CHECKING
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QFormLayout, QTextEdit, QMessageBox, QFileDialog,
    QCheckBox, QProgressBar, QRadioButton, QButtonGroup, QScrollArea, QGridLayout
)
from qt_compat.core import Qt, Signal, QThread, QTimer

from config.common import OUTPUT_DIR, get_dynamic_file_path
from classes.theme import get_color, ThemeKey
from classes.utils.themed_checkbox_delegate import ThemedCheckboxDelegate
from classes.managers.log_manager import get_logger
from ..core.auth_manager import get_auth_manager
if TYPE_CHECKING:
    from ..core.portal_client import PortalClient
    from ..core.uploader import Uploader

logger = get_logger("DataPortal.DatasetUploadTab")


class UploadWorker(QThread):
    """アップロード処理を行うワーカースレッド"""
    progress = Signal(str)  # 進捗メッセージ
    finished = Signal(bool, str)  # 成功フラグ, メッセージ
    
    def __init__(self, uploader: Uploader, json_path: str):
        super().__init__()
        self.uploader = uploader
        self.json_path = json_path
    
    def run(self):
        """アップロード実行"""
        try:
            self.progress.emit(f"アップロード開始: {Path(self.json_path).name}")
            success, message = self.uploader.upload_json_file(self.json_path)
            self.finished.emit(success, message)
        except Exception as e:
            self.finished.emit(False, f"アップロードエラー: {e}")
class ContentsZipUploadWorker(QThread):
    """コンテンツZIPアップロード処理を行うワーカースレッド"""

    progress = Signal(str)  # 進捗メッセージ
    finished = Signal(bool, str)  # 成功フラグ, メッセージ

    def __init__(self, uploader: Uploader, t_code: str, zip_path: str):
        super().__init__()
        self.uploader = uploader
        self.t_code = t_code
        self.zip_path = zip_path

    def run(self):
        try:
            self.progress.emit(f"ZIPアップロード開始: {Path(self.zip_path).name}")
            success, message = self.uploader.upload_contents_zip(self.t_code, self.zip_path)
            self.finished.emit(success, message)
        except Exception as e:
            self.finished.emit(False, f"ZIPアップロードエラー: {e}")


class DatasetUploadTab(QWidget):
    """
    データセットJSONアップロードタブ
    
    機能:
    - ファイル直接選択
    - データセットコンボボックス検索選択
    - 匿名化オプション
    - アップロード実行
    """
    
    upload_completed = Signal(bool, str)  # 成功フラグ, メッセージ
    
    def __init__(self, parent=None):
        """初期化"""
        super().__init__(parent)
        
        self.auth_manager = get_auth_manager()
        self.portal_client = None
        self.uploader = None
        self.upload_worker = None
        self.contents_zip_upload_worker = None
        self.selected_json_path = None
        self.selected_zip_path = None
        self.current_dataset_id = None  # 現在選択中のデータセットID
        self.json_uploaded = False  # JSONアップロード完了フラグ
        self.current_t_code = None  # 現在のt_code（画像アップロード用）
        self.current_status = None  # 現在のステータス（'公開済' or '非公開'）
        self.current_environment = None  # 現在の環境（production/test）
        self.current_public_code = None  # 公開ページURL用 code
        self.current_public_key = None   # 公開ページURL用 key
        self._existing_images_cache: Dict[str, Set[str]] = {}
        self._image_caption_cache: Dict[str, str] = {}

        # データセットドロップダウン（重い生成処理）の遅延初期化
        self._dataset_dropdown_initialized = False
        self._dataset_dropdown_init_scheduled = False
        self._dataset_dropdown_init_timer = None
        
        self._init_ui()
        logger.info("データセットアップロードタブ初期化完了")
        # テーマ変更時に再適用
        try:
            from classes.theme.theme_manager import ThemeManager
            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        except Exception as e:
            logger.debug(f"DatasetUploadTab theme signal connect failed: {e}")
        self.refresh_theme()
    
    def _init_ui(self):
        """UI初期化"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer_layout.addWidget(self._scroll_area)

        scroll_widget = QWidget()
        self._scroll_area.setWidget(scroll_widget)

        layout = QVBoxLayout(scroll_widget)
        layout.setSpacing(10)

        # ステータス表示エリアを先に作成（他のUIコンポーネントがログ出力に使用するため）
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(200)
        self.status_text.setPlaceholderText("アップロードログがここに表示されます...")
        self._apply_status_style()

        # 環境選択セクション
        env_group = self._create_environment_selector()
        layout.addWidget(env_group)

        # ファイル選択セクション
        file_group = self._create_file_selector()
        layout.addWidget(file_group)

        # 匿名化オプションセクション
        anon_group = self._create_anonymization_options()
        layout.addWidget(anon_group)

        # アップロードボタン
        upload_layout = self._create_upload_button_section()
        layout.addLayout(upload_layout)

        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # ステータス表示エリアを追加
        layout.addWidget(QLabel("ステータス:"))
        layout.addWidget(self.status_text)

        # 初期表示設定（データセット検索がデフォルト）
        self._on_file_mode_changed()

        layout.addStretch()
    
    def _apply_status_style(self):
        """ステータステキストスタイルを適用"""
        self.status_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 4px;
                padding: 8px;
            }}
        """)
    
    def refresh_theme(self):
        """テーマ変更時のスタイル更新"""
        try:
            # ルート背景
            self.setStyleSheet(f"background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};")
            self._apply_status_style()
            # 入力系
            from qt_compat.widgets import QLineEdit, QComboBox, QPushButton, QGroupBox, QRadioButton, QCheckBox, QTextEdit
            # QLineEdit
            for w in self.findChildren(QLineEdit):
                w.setStyleSheet(f"QLineEdit {{ background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; color: {get_color(ThemeKey.INPUT_TEXT)}; border: 1px solid {get_color(ThemeKey.INPUT_BORDER)}; border-radius: 4px; padding: 4px 6px; }}")
            # QComboBox - フォントが隠れないように高さとパディング調整
            combo_style = f"""QComboBox {{
                background-color: {get_color(ThemeKey.COMBO_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: 1px solid {get_color(ThemeKey.COMBO_BORDER)};
                border-radius: 4px;
                padding: 6px 8px;
                min-height: 28px;
                font-size: 10pt;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                width: 12px;
                height: 12px;
            }}"""
            for w in self.findChildren(QComboBox):
                w.setStyleSheet(combo_style)
            # Buttons (簡易共通適用 - variant未設定のみ)
            pressed_bg_key = getattr(
                ThemeKey,
                "BUTTON_SECONDARY_BACKGROUND_PRESSED",
                ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER,
            )
            btn_style_default = (
                f"QPushButton {{ background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)}; border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)}; border-radius: 4px; padding: 6px 10px; font-weight: bold; }} "
                f"QPushButton:hover {{ background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)}; }} "
                f"QPushButton:pressed {{ background-color: {get_color(pressed_bg_key)}; }} "
                f"QPushButton:disabled {{ background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)}; color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)}; border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)}; }}"
            )
            for b in self.findChildren(QPushButton):
                if not b.property("variant"):
                    b.setStyleSheet(btn_style_default)

            # DatasetUploadTab 内の主要アクションボタンは個別スタイルを持つため、
            # refresh_theme で上書きされた後に再適用してテーマ追従させる。
            self._apply_action_button_styles()
            # GroupBox
            gb_style = f"QGroupBox {{ border: 1px solid {get_color(ThemeKey.PANEL_BORDER)}; border-radius: 6px; margin-top: 8px; background-color: {get_color(ThemeKey.PANEL_BACKGROUND)}; }} QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 2px 4px; color: {get_color(ThemeKey.TEXT_SECONDARY)}; font-weight: bold; }}"
            for g in self.findChildren(QGroupBox):
                g.setStyleSheet(gb_style)
            # Radio / Checkbox
            indicator_style = (
                f"QRadioButton {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }} QRadioButton::indicator {{ width:16px; height:16px; border:1px solid {get_color(ThemeKey.INPUT_BORDER)}; background:{get_color(ThemeKey.INPUT_BACKGROUND)}; border-radius:8px; }} QRadioButton::indicator:checked {{ background:{get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; }}"
                f" QCheckBox {{ color: {get_color(ThemeKey.TEXT_PRIMARY)}; }} QCheckBox::indicator {{ width:16px; height:16px; border:1px solid {get_color(ThemeKey.INPUT_BORDER)}; background:{get_color(ThemeKey.INPUT_BACKGROUND)}; border-radius:3px; }} QCheckBox::indicator:checked {{ background:{get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; border-color:{get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)}; }}"
            )
            for r in self.findChildren(QRadioButton):
                r.setStyleSheet(indicator_style)
            for c in self.findChildren(QCheckBox):
                c.setStyleSheet(indicator_style)
            # Status text already handled
            self._apply_file_list_theme()
            self.update()
        except Exception as e:
            logger.debug(f"DatasetUploadTab refresh_theme failed: {e}")

    def _apply_action_button_styles(self) -> None:
        """主要アクションボタンのスタイルをテーマに合わせて再適用"""
        try:
            # 画像ファイル一括取得
            if hasattr(self, "bulk_download_btn") and self.bulk_download_btn is not None:
                self.bulk_download_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                        padding: 8px 16px;
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                    }}
                    QPushButton:disabled {{
                        background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
                    }}
                    """
                )

            # 画像アップロード
            if hasattr(self, "upload_images_btn") and self.upload_images_btn is not None:
                self.upload_images_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
                        padding: 8px 16px;
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)};
                    }}
                    QPushButton:disabled {{
                        background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
                    }}
                    """
                )

            # 書誌情報JSONアップロード
            if hasattr(self, "upload_btn") and self.upload_btn is not None:
                self.upload_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                        padding: 10px 20px;
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
                    }}
                    QPushButton:disabled {{
                        background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
                    }}
                    """
                )

            # データカタログ修正
            if hasattr(self, "edit_portal_btn") and self.edit_portal_btn is not None:
                self.edit_portal_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                        padding: 10px 20px;
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                    }}
                    QPushButton:disabled {{
                        background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
                    }}
                    """
                )

            # コンテンツZIPアップロード
            if hasattr(self, "upload_zip_btn") and self.upload_zip_btn is not None:
                self.upload_zip_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                        padding: 10px 20px;
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                    }}
                    QPushButton:disabled {{
                        background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
                    }}
                    """
                )

            # 公開ページ表示
            if hasattr(self, "public_view_btn") and self.public_view_btn is not None:
                self.public_view_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                        padding: 10px 20px;
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                    }}
                    QPushButton:disabled {{
                        background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
                    }}
                    """
                )

            # ステータス変更
            if hasattr(self, "toggle_status_btn") and self.toggle_status_btn is not None:
                self.toggle_status_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
                        padding: 10px 20px;
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)};
                    }}
                    QPushButton:disabled {{
                        background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_DISABLED_BORDER)};
                    }}
                    """
                )
        except Exception as e:
            logger.debug(f"DatasetUploadTab _apply_action_button_styles failed: {e}")

    def _apply_file_list_theme(self) -> None:
        """取得済みファイル一覧テーブルとプレビュー領域のテーマ追従を保証"""
        try:
            if hasattr(self, 'file_list_widget') and self.file_list_widget is not None:
                self.file_list_widget.setStyleSheet(f"""
                    QTableWidget {{
                        background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                        color: {get_color(ThemeKey.TEXT_PRIMARY)};
                        border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                        gridline-color: {get_color(ThemeKey.BORDER_DEFAULT)};
                        alternate-background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                    }}
                    QHeaderView::section {{
                        background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                        color: {get_color(ThemeKey.TEXT_SECONDARY)};
                        border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                        padding: 4px 6px;
                        font-weight: bold;
                    }}
                    QTableWidget::item:selected {{
                        background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                    }}
                """)

            if hasattr(self, 'thumbnail_title_label') and self.thumbnail_title_label is not None:
                self.thumbnail_title_label.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.TEXT_MUTED)};")
            if hasattr(self, 'thumbnail_label') and self.thumbnail_label is not None:
                self.thumbnail_label.setStyleSheet(
                    f"border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; "
                    f"background: {get_color(ThemeKey.PANEL_BACKGROUND)}; "
                    f"color: {get_color(ThemeKey.TEXT_PRIMARY)};"
                )
        except Exception as exc:
            logger.debug(f"DatasetUploadTab _apply_file_list_theme failed: {exc}")
    
    def _create_environment_selector(self) -> QGroupBox:
        """環境選択セクション"""
        group = QGroupBox("アップロード先環境")
        layout = QFormLayout()
        
        self.env_combo = QComboBox()
        self.env_combo.currentTextChanged.connect(self._on_environment_changed)
        layout.addRow("環境:", self.env_combo)
        
        # 環境情報を読み込み
        self._load_environments()
        
        group.setLayout(layout)
        return group
    
    def _create_file_selector(self) -> QGroupBox:
        """ファイル選択セクション"""
        group = QGroupBox("JSONファイル選択")
        layout = QVBoxLayout()
        
        # 選択方法ラジオボタン
        radio_layout = QHBoxLayout()
        self.file_mode_group = QButtonGroup()
        
        self.direct_file_radio = QRadioButton("ファイル直接選択")
        self.direct_file_radio.toggled.connect(self._on_file_mode_changed)
        self.file_mode_group.addButton(self.direct_file_radio, 0)
        radio_layout.addWidget(self.direct_file_radio)
        
        self.dataset_search_radio = QRadioButton("データセット検索")
        self.dataset_search_radio.setChecked(True)
        self.dataset_search_radio.toggled.connect(self._on_file_mode_changed)
        self.file_mode_group.addButton(self.dataset_search_radio, 1)
        radio_layout.addWidget(self.dataset_search_radio)
        
        radio_layout.addStretch()
        layout.addLayout(radio_layout)
        
        # ファイル直接選択UI
        self.direct_file_widget = QWidget()
        direct_layout = QHBoxLayout(self.direct_file_widget)
        direct_layout.setContentsMargins(0, 0, 0, 0)
        
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText("JSONファイルのパスを入力または参照ボタンで選択")
        self.file_path_input.setReadOnly(True)
        direct_layout.addWidget(self.file_path_input)
        
        self.browse_btn = QPushButton("📁 参照")
        self.browse_btn.clicked.connect(self._on_browse_file)
        direct_layout.addWidget(self.browse_btn)
        
        layout.addWidget(self.direct_file_widget)
        
        # データセット検索UI（データ取得2と共有）
        self.dataset_search_widget = QWidget()
        dataset_layout = QVBoxLayout(self.dataset_search_widget)
        dataset_layout.setContentsMargins(0, 0, 0, 0)

        # データセットドロップダウンは生成が重いので、初回ペイント後に遅延生成する
        self._dataset_dropdown_container = QWidget(self.dataset_search_widget)
        self._dataset_dropdown_container_layout = QVBoxLayout(self._dataset_dropdown_container)
        self._dataset_dropdown_container_layout.setContentsMargins(0, 0, 0, 0)
        self._dataset_dropdown_placeholder_label = QLabel("データセット一覧を準備中...")
        self._dataset_dropdown_container_layout.addWidget(self._dataset_dropdown_placeholder_label)
        dataset_layout.addWidget(self._dataset_dropdown_container)
        
        # 選択されたデータセット情報表示
        self.dataset_info_label = QLabel("")
        self.dataset_info_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px;")
        self.dataset_info_label.setWordWrap(True)
        dataset_layout.addWidget(self.dataset_info_label)
        
        # 画像ファイル一括取得ボタン
        file_download_row = QHBoxLayout()
        
        self.bulk_download_btn = QPushButton("📥 画像ファイル一括取得")
        self.bulk_download_btn.setEnabled(False)
        self.bulk_download_btn.clicked.connect(self._on_bulk_download)
        self.bulk_download_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)
        file_download_row.addWidget(self.bulk_download_btn)
        
        self.open_files_folder_btn = QPushButton("📂 フォルダを開く")
        self.open_files_folder_btn.setEnabled(False)
        self.open_files_folder_btn.clicked.connect(self._on_open_files_folder)
        file_download_row.addWidget(self.open_files_folder_btn)
        
        file_download_row.addStretch()
        
        dataset_layout.addLayout(file_download_row)
        
        # 画像ファイルリスト表示エリア（横並び）
        self.file_list_group = QGroupBox("取得済みファイル一覧")
        self.file_list_group.setVisible(False)
        file_list_main_layout = QHBoxLayout()  # 横並びに変更
        
        # 左側: ファイルリストエリア
        file_list_left_container = QWidget()
        file_list_left_layout = QVBoxLayout(file_list_left_container)
        file_list_left_layout.setContentsMargins(0, 0, 0, 0)
        
        # チェックボックス操作ボタン
        checkbox_button_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全選択")
        self.select_all_btn.clicked.connect(self._on_select_all_files)
        self.select_all_btn.setMaximumWidth(80)
        checkbox_button_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("全解除")
        self.deselect_all_btn.clicked.connect(self._on_deselect_all_files)
        self.deselect_all_btn.setMaximumWidth(80)
        checkbox_button_layout.addWidget(self.deselect_all_btn)
        
        checkbox_button_layout.addStretch()
        file_list_left_layout.addLayout(checkbox_button_layout)
        
        # ファイルリスト（ヘッダ付き・ソート可能・キャプション編集可）
        from qt_compat.widgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
        from qt_compat.core import Qt

        self.file_list_widget = QTableWidget()
        self.file_list_widget.setColumnCount(4)
        self.file_list_widget.setHorizontalHeaderLabels(["選択", "ファイル名", "キャプション", "アップロード"])
        self.file_list_widget.setSortingEnabled(True)
        self.file_list_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.file_list_widget.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.file_list_widget.verticalHeader().setVisible(False)
        self.file_list_widget.setAlternatingRowColors(True)
        self.file_list_widget.installEventFilter(self)  # キーボードイベント（スペース）
        self.file_list_widget.currentCellChanged.connect(self._on_file_table_current_cell_changed)
        self.file_list_widget.itemChanged.connect(self._on_file_table_item_changed)

        # 「選択」列のチェックボックスをテーマ準拠で描画（チェック状態が分かりやすいようにする）
        try:
            self.file_list_widget.setItemDelegateForColumn(0, ThemedCheckboxDelegate(self.file_list_widget))
        except Exception as e:
            logger.debug(f"file_list_widget checkbox delegate apply failed: {e}")

        header = self.file_list_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.file_list_widget.setMaximumHeight(300)
        self.file_list_widget.setStyleSheet(f"""
            QTableWidget {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                gridline-color: {get_color(ThemeKey.BORDER_DEFAULT)};
            }}
            QHeaderView::section {{
                background-color: {get_color(ThemeKey.PANEL_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_SECONDARY)};
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                padding: 4px 6px;
                font-weight: bold;
            }}
            QTableWidget::item:selected {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
            }}
        """)

        file_list_left_layout.addWidget(self.file_list_widget)
        
        file_list_main_layout.addWidget(file_list_left_container)
        
        # サムネイルプレビューラベル
        thumbnail_container = QWidget()
        thumbnail_layout = QVBoxLayout(thumbnail_container)
        thumbnail_layout.setContentsMargins(10, 0, 0, 0)
        
        self.thumbnail_title_label = QLabel("プレビュー")
        self.thumbnail_title_label.setStyleSheet(f"font-weight: bold; color: {get_color(ThemeKey.TEXT_MUTED)};")
        thumbnail_layout.addWidget(self.thumbnail_title_label)
        
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(200, 200)
        self.thumbnail_label.setAlignment(Qt.AlignCenter)
        self.thumbnail_label.setStyleSheet(
            f"border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)}; "
            f"background: {get_color(ThemeKey.PANEL_BACKGROUND)}; "
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)};"
        )
        self.thumbnail_label.setText("ファイルにマウスオーバーで\nプレビューを表示")
        thumbnail_layout.addWidget(self.thumbnail_label)
        thumbnail_layout.addStretch()
        
        file_list_main_layout.addWidget(thumbnail_container)
        
        self.file_list_group.setLayout(file_list_main_layout)
        dataset_layout.addWidget(self.file_list_group)
        
        # 画像アップロードボタン
        image_upload_row = QHBoxLayout()
        
        self.upload_images_btn = QPushButton("📤 画像アップロード")
        self.upload_images_btn.setEnabled(False)
        self.upload_images_btn.clicked.connect(self._on_upload_images)
        self.upload_images_btn.setToolTip("書誌情報JSONをアップロード後に使用可能になります")
        self.upload_images_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)
        image_upload_row.addWidget(self.upload_images_btn)
        image_upload_row.addStretch()
        
        dataset_layout.addLayout(image_upload_row)
        
        layout.addWidget(self.dataset_search_widget)
        self.dataset_search_widget.setVisible(False)
        
        group.setLayout(layout)
        return group

    def _schedule_dataset_dropdown_init(self) -> None:
        if self._dataset_dropdown_initialized or self._dataset_dropdown_init_scheduled:
            return
        self._dataset_dropdown_init_scheduled = True
        # NOTE: QTimer.singleShot は親を持たない遅延呼び出しとなり、Widget破棄後に
        # bound method が呼ばれてWindowsでaccess violationになることがある。
        # 親付きの単発タイマーにして、破棄と同時に自動停止/破棄されるようにする。
        try:
            if self._dataset_dropdown_init_timer is None:
                self._dataset_dropdown_init_timer = QTimer(self)
                self._dataset_dropdown_init_timer.setSingleShot(True)
                self._dataset_dropdown_init_timer.timeout.connect(self._ensure_dataset_dropdown_initialized)
            self._dataset_dropdown_init_timer.start(0)
        except Exception:
            QTimer.singleShot(0, self._ensure_dataset_dropdown_initialized)

    def _ensure_dataset_dropdown_initialized(self) -> None:
        if self._dataset_dropdown_initialized:
            self._dataset_dropdown_init_scheduled = False
            return

        self._dataset_dropdown_init_scheduled = False

        try:
            from classes.data_fetch2.core.ui.data_fetch2_widget import create_dataset_dropdown_all

            dataset_json_path = get_dynamic_file_path("output/rde/data/dataset.json")
            self.dataset_dropdown_widget = create_dataset_dropdown_all(
                dataset_json_path,
                self,
                global_share_filter="both",
            )

            if hasattr(self.dataset_dropdown_widget, 'dataset_dropdown'):
                self.dataset_dropdown_widget.dataset_dropdown.currentIndexChanged.connect(
                    self._on_dataset_selected_advanced
                )

            # placeholder と置換
            if hasattr(self, '_dataset_dropdown_container_layout'):
                while self._dataset_dropdown_container_layout.count():
                    item = self._dataset_dropdown_container_layout.takeAt(0)
                    w = item.widget()
                    if w is not None:
                        w.setParent(None)
                self._dataset_dropdown_container_layout.addWidget(self.dataset_dropdown_widget)

            self._log_status("✅ データ取得2の高度なドロップダウンを統合しました")
            self._dataset_dropdown_initialized = True
            return

        except ImportError as e:
            logger.error(f"データセットドロップダウン統合失敗: {e}")
            self._log_status("⚠️ 高度なドロップダウン統合失敗、シンプル版を使用します", error=True)

        # フォールバック: シンプル版
        search_row = QHBoxLayout()
        self.dataset_combo = QComboBox()
        self.dataset_combo.setEditable(True)
        self.dataset_combo.setInsertPolicy(QComboBox.NoInsert)
        self.dataset_combo.setPlaceholderText("データセットを検索...")
        self.dataset_combo.setMinimumWidth(500)
        self.dataset_combo.currentIndexChanged.connect(self._on_dataset_selected)
        search_row.addWidget(self.dataset_combo)

        self.load_datasets_btn = QPushButton("🔄 データセット読込")
        self.load_datasets_btn.clicked.connect(self._on_load_datasets)
        search_row.addWidget(self.load_datasets_btn)

        # placeholder と置換
        if hasattr(self, '_dataset_dropdown_container_layout'):
            while self._dataset_dropdown_container_layout.count():
                item = self._dataset_dropdown_container_layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
            self._dataset_dropdown_container_layout.addLayout(search_row)

            # 選択中データセットの日時（JST）+ サブグループ名を表示
            try:
                from classes.utils.dataset_datetime_display import create_dataset_dates_label, attach_dataset_dates_label_with_subgroup

                self._dataset_dates_label = create_dataset_dates_label(self)
                attach_dataset_dates_label_with_subgroup(combo=self.dataset_combo, label=self._dataset_dates_label)
                self._dataset_dropdown_container_layout.addWidget(self._dataset_dates_label)
            except Exception:
                self._dataset_dates_label = None

        self._dataset_dropdown_initialized = True

    def select_dataset_id(self, dataset_id: str) -> bool:
        """指定dataset_idをデータセット選択UIへ反映する。

        - 高度ドロップダウン(data_fetch2統合)があればそれを優先
        - フォールバックのQComboBoxでも選択できる
        """

        dsid = str(dataset_id or "").strip()
        if not dsid:
            return False

        try:
            if not self._dataset_dropdown_initialized:
                self._ensure_dataset_dropdown_initialized()
        except Exception:
            pass

        # 1) 高度ドロップダウン（data_fetch2統合）
        try:
            dropdown_widget = getattr(self, "dataset_dropdown_widget", None)
            combo = getattr(dropdown_widget, "dataset_dropdown", None) if dropdown_widget is not None else None
            if combo is not None and hasattr(combo, "count"):
                try:
                    from classes.data_fetch2.core.ui.data_fetch2_widget import relax_fetch2_filters_for_launch

                    relax_fetch2_filters_for_launch(dropdown_widget)
                except Exception:
                    pass

                def _find_index() -> int:
                    for i in range(int(combo.count())):
                        try:
                            if str(combo.itemData(i) or "").strip() == dsid:
                                return int(i)
                        except Exception:
                            continue
                    return -1

                idx = _find_index()
                if idx < 0:
                    try:
                        reload_fn = getattr(dropdown_widget, "reload_datasets", None)
                        if callable(reload_fn):
                            reload_fn()
                    except Exception:
                        pass
                    idx = _find_index()

                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    try:
                        combo.setFocus()
                    except Exception:
                        pass
                    return True
        except Exception:
            pass

        # 2) フォールバックのQComboBox
        try:
            combo = getattr(self, "dataset_combo", None)
            if combo is None:
                return False

            try:
                if int(combo.count()) <= 1:
                    self._on_load_datasets()
            except Exception:
                pass

            for i in range(int(combo.count())):
                try:
                    info = combo.itemData(i)
                    if isinstance(info, dict) and str(info.get("id") or "").strip() == dsid:
                        combo.setCurrentIndex(i)
                        try:
                            combo.setFocus()
                        except Exception:
                            pass
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        return False
    
    def _create_anonymization_options(self) -> QGroupBox:
        """匿名化オプションセクション"""
        group = QGroupBox("匿名化設定")
        layout = QVBoxLayout()
        
        self.anonymize_checkbox = QCheckBox("アップロード前にJSONを匿名化する")
        self.anonymize_checkbox.setToolTip(
            "チェックを入れると、アップロード前に自動的にJSONを匿名化します\n"
            "（name, subjectTitle を非開示情報に置換、grantNumber はJSONから自動取得）"
        )
        layout.addWidget(self.anonymize_checkbox)
        
        info_label = QLabel(
            "💡 課題番号は元のJSONファイルから自動的に取得されます"
        )
        info_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 10px;")
        layout.addWidget(info_label)
        
        group.setLayout(layout)
        return group
    
    def _create_upload_button_section(self) -> QVBoxLayout:
        """アップロードボタンセクション

        NOTE: ボタン数が増えたため、デフォルト幅でも横スクロールが出にくいよう2段構成にする。
        """

        layout = QVBoxLayout()

        # 1段目: 検証
        top_row = QHBoxLayout()
        self.validate_btn = QPushButton("✓ ファイル検証")
        self.validate_btn.clicked.connect(self._on_validate_file)
        top_row.addWidget(self.validate_btn)
        top_row.addStretch()
        layout.addLayout(top_row)

        # 2段目: アクションボタン群（グリッドで折り返し）
        action_grid = QGridLayout()
        action_grid.setHorizontalSpacing(10)
        action_grid.setVerticalSpacing(8)
        action_grid.setContentsMargins(0, 0, 0, 0)

        # 書誌情報JSONアップロードボタン
        self.upload_btn = QPushButton("📤 書誌情報JSONアップロード")
        self.upload_btn.setEnabled(False)
        self.upload_btn.clicked.connect(self._on_upload)
        self.upload_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)

        # コンテンツZIPアップロードボタン（データカタログ修正が有効な場合のみ）
        self.upload_zip_btn = QPushButton("📦 コンテンツZIPアップロード")
        self.upload_zip_btn.setEnabled(False)
        self.upload_zip_btn.clicked.connect(self._on_upload_zip)
        self.upload_zip_btn.setToolTip("ローカルZIPアップロード、またはRDEから自動取得してZIP化→アップロードを選択できます")
        self.upload_zip_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)

        # データポータル修正ボタン
        self.edit_portal_btn = QPushButton("✏️ データカタログ修正")
        self.edit_portal_btn.setEnabled(False)
        self.edit_portal_btn.clicked.connect(self._on_edit_portal)
        self.edit_portal_btn.setToolTip("データポータルに登録済みのエントリを修正します")
        self.edit_portal_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)

        # ブラウザ表示ボタン（公開ページ）
        self.public_view_btn = QPushButton("🌐 ブラウザで表示")
        self.public_view_btn.setEnabled(False)
        self.public_view_btn.clicked.connect(self._on_open_public_view)
        self.public_view_btn.setToolTip("データポータル公開ページを既定ブラウザで開きます")
        self.public_view_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)

        # ステータス変更ボタン
        self.toggle_status_btn = QPushButton("🔄 ステータス変更")
        self.toggle_status_btn.setEnabled(False)
        self.toggle_status_btn.clicked.connect(self._on_toggle_status)
        self.toggle_status_btn.setToolTip("データポータルの公開/非公開ステータスを切り替えます")
        self.toggle_status_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_WARNING_TEXT)};
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)

        # 配置（3列×2行）
        action_grid.addWidget(self.upload_btn, 0, 0)
        action_grid.addWidget(self.upload_zip_btn, 0, 1)
        action_grid.addWidget(self.edit_portal_btn, 0, 2)
        action_grid.addWidget(self.public_view_btn, 1, 0)
        action_grid.addWidget(self.toggle_status_btn, 1, 1)

        layout.addLayout(action_grid)

        # コンテンツZIPアップ済み表示（コンテンツリンク有無で判定）
        self.contents_zip_status_label = QLabel("")
        self.contents_zip_status_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 11px;")
        self.contents_zip_status_label.setText("📦 コンテンツZIP: 未確認")
        layout.addWidget(self.contents_zip_status_label)

        return layout

    def _update_contents_zip_status_label(self, has_contents_link: bool | None) -> None:
        """コンテンツZIPアップ済み表示を更新。"""
        try:
            if not hasattr(self, "contents_zip_status_label") or self.contents_zip_status_label is None:
                return

            if has_contents_link is True:
                self.contents_zip_status_label.setText("✅ コンテンツZIPアップ済み")
                self.contents_zip_status_label.setStyleSheet(
                    f"color: {get_color(ThemeKey.TEXT_SUCCESS)}; font-size: 11px;"
                )
                return
            if has_contents_link is False:
                self.contents_zip_status_label.setText("📦 コンテンツZIP未アップロード")
                self.contents_zip_status_label.setStyleSheet(
                    f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 11px;"
                )
                return

            self.contents_zip_status_label.setText("📦 コンテンツZIP: 未確認")
            self.contents_zip_status_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 11px;")
        except Exception:
            pass
    
    def _load_environments(self):
        """環境一覧を読み込み"""
        from ..conf.config import get_data_portal_config
        
        config = get_data_portal_config()
        environments = config.get_available_environments()
        
        self.env_combo.clear()
        for env in environments:
            # 表示名を統一（テスト環境 or 本番環境のみ）
            if env == "production":
                display_name = "本番環境"
            elif env == "test":
                display_name = "テスト環境"
            else:
                # test, production以外は表示しない（既にフィルタ済みだが念のため）
                continue
            self.env_combo.addItem(display_name, env)
    
    def _on_environment_changed(self, display_name: str):
        """環境変更時の処理"""
        environment = self.env_combo.currentData()
        if not environment:
            return
        
        self._log_status(f"環境選択: {display_name}")
        
        # 現在の環境を保持
        self.current_environment = environment
        self._existing_images_cache.clear()
        
        # PortalClientを作成（環境が変わったら再作成）
        from ..core.portal_client import PortalClient
        self.portal_client = PortalClient(environment=environment)
        
        # 認証情報チェックと自動読込
        if self.auth_manager.has_credentials(environment):
            # 認証情報があればクライアントに設定
            credentials = self.auth_manager.get_credentials(environment)
            if credentials:
                self.portal_client.set_credentials(credentials)
                self._log_status(f"✅ 保存済み認証情報を読み込みました")
        else:
            self._log_status(
                f"⚠️ {display_name}の認証情報が保存されていません。\n"
                "「ログイン設定」タブで認証情報を保存してください。",
                error=True
            )
    
    def _on_file_mode_changed(self):
        """ファイル選択モード変更"""
        is_direct = self.direct_file_radio.isChecked()
        
        self.direct_file_widget.setVisible(is_direct)
        self.dataset_search_widget.setVisible(not is_direct)

        if not is_direct:
            self._schedule_dataset_dropdown_init()
        
        # 選択解除
        self.selected_json_path = None
        self.selected_zip_path = None
        self.upload_btn.setEnabled(False)
        try:
            if hasattr(self, "upload_zip_btn") and self.upload_zip_btn is not None:
                self.upload_zip_btn.setEnabled(False)
        except Exception:
            pass
        
        mode_name = "ファイル直接選択" if is_direct else "データセット検索"
        self._log_status(f"選択モード: {mode_name}")
    
    def _on_browse_file(self):
        """ファイル参照ダイアログ"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "JSONファイルを選択",
            get_dynamic_file_path("output/datasets"),
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.file_path_input.setText(file_path)
            self.selected_json_path = file_path
            self.upload_btn.setEnabled(True)
            self._log_status(f"ファイル選択: {Path(file_path).name}")
    
    def _on_load_datasets(self):
        """データセット一覧を読み込み"""
        self._log_status("データセット一覧読み込み中...")
        
        try:
            from config.common import get_dynamic_file_path
            import json
            
            # 正しいパス: output/rde/data/dataset.json
            dataset_json_path = get_dynamic_file_path("output/rde/data/dataset.json")
            
            if not os.path.exists(dataset_json_path):
                self._log_status(f"❌ dataset.jsonが見つかりません: {dataset_json_path}", error=True)
                return
            
            # JSONファイルを読み込み
            with open(dataset_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # データ構造を確認
            if isinstance(data, dict) and 'data' in data:
                datasets = data['data']
            elif isinstance(data, list):
                datasets = data
            else:
                self._log_status("❌ 不正なデータ構造です", error=True)
                return
            
            # コンボボックスをクリア
            self.dataset_combo.clear()
            self.dataset_combo.addItem("-- データセットを選択 --", None)
            
            # データセット一覧を追加
            for dataset in datasets:
                if not isinstance(dataset, dict):
                    continue
                
                dataset_id = dataset.get('id', '')
                attrs = dataset.get('attributes', {})
                name = attrs.get('name', '名前なし')
                grant_number = attrs.get('grantNumber', '')
                dataset_type = attrs.get('datasetType', '')
                
                # 表示テキスト作成
                display_parts = []
                if grant_number:
                    display_parts.append(f"[{grant_number}]")
                display_parts.append(name)
                if dataset_type:
                    display_parts.append(f"({dataset_type})")
                display_parts.append(f"ID:{dataset_id}")
                
                display_text = ' '.join(display_parts)
                
                # データセット情報を保存
                dataset_info = {
                    'id': dataset_id,
                    'name': name,
                    'grantNumber': grant_number,
                    'datasetType': dataset_type,
                    'attributes': attrs
                }
                
                self.dataset_combo.addItem(display_text, dataset_info)
            
            # QCompleter設定（検索補完機能）
            from qt_compat.core import Qt
            from qt_compat.widgets import QCompleter
            
            completer = QCompleter([self.dataset_combo.itemText(i) for i in range(self.dataset_combo.count())])
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            self.dataset_combo.setCompleter(completer)
            
            self._log_status(f"✅ データセット読み込み完了: {len(datasets)}件")
            
        except Exception as e:
            logger.error(f"データセット読み込みエラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_status(f"❌ データセット読み込みエラー: {e}", error=True)
    
    def _on_dataset_selected_advanced(self, index: int):
        """高度なドロップダウンからデータセット選択時の処理"""
        # data_fetch2 の create_dataset_dropdown_all() は「ダミー項目を追加しない」ため、
        # index=0 が先頭データセットになる。
        # そのため index だけでプレースホルダ判定しない。
        if index < 0:
            self.upload_btn.setEnabled(False)
            return
        
        try:
            # 高度なドロップダウンからデータセットIDを取得
            combo = self.dataset_dropdown_widget.dataset_dropdown
            dataset_id = combo.itemData(index)
            
            if not dataset_id:
                self.upload_btn.setEnabled(False)
                return
            
            # データセットが変わったらJSONアップロードフラグをリセット
            self.json_uploaded = False
            self.current_t_code = None
            
            # dataset.jsonからデータセット情報を取得
            dataset_info = self._get_dataset_info_from_json(dataset_id)
            
            if not dataset_info:
                self.dataset_info_label.setText(f"⚠️ データセット情報取得失敗: {dataset_id}")
                self._log_status(f"❌ データセット情報取得失敗: {dataset_id}", error=True)
                self.upload_btn.setEnabled(False)
                return
            
            dataset_name = dataset_info.get('name', '不明')
            grant_number = dataset_info.get('grantNumber', '')
            
            # JSONファイルパスを探す
            json_path = self._find_dataset_json(dataset_id, grant_number)
            
            if json_path:
                self.selected_json_path = json_path
                self.upload_btn.setEnabled(True)
                
                # 画像ファイルの取得状況を確認
                files_exist, file_count, file_list = self._check_files_exist(dataset_id)
                
                # ボタンの状態を設定
                self.bulk_download_btn.setEnabled(True)
                
                # 既存ファイルがある場合はチェックマークを表示
                if files_exist:
                    self.bulk_download_btn.setText(f"✅ 📥 画像ファイル一括取得 ({file_count}件取得済み)")
                    self.open_files_folder_btn.setEnabled(True)
                else:
                    self.bulk_download_btn.setText("📥 画像ファイル一括取得")
                    # フォルダが存在すればボタンを有効化
                    folder_exists = self._check_folder_exists(dataset_id, grant_number)
                    self.open_files_folder_btn.setEnabled(folder_exists)
                
                info_text = (
                    f"データセット: {dataset_name}\n"
                    f"ID: {dataset_id}\n"
                    f"JSONファイル: {Path(json_path).name}\n"
                    f"画像ファイル: {'取得済み' if files_exist else '未取得'}"
                )
                if files_exist:
                    info_text += f" ({file_count}件)"
                
                self.dataset_info_label.setText(info_text)
                self._log_status(f"データセット選択: {dataset_name}")
                
                # 現在選択中のデータセットIDを保存
                self.current_dataset_id = dataset_id
                
                # RDEサイト上にデータセットが存在するか確認
                rde_exists = self._check_rde_dataset_exists(dataset_id)
                
                if not rde_exists:
                    # RDEサイトにデータセットが存在しない場合
                    self.dataset_info_label.setText(
                        f"⚠️ RDEサイト上にデータセットが存在しません\n"
                        f"データセット: {dataset_name}\n"
                        f"ID: {dataset_id}\n"
                        f"\n※RDEサイトでデータセットを開設してください"
                    )
                    self._log_status(f"❌ RDEサイト上にデータセットが存在しません: {dataset_id}", error=True)
                    
                    # 全ボタンを無効化
                    self.bulk_download_btn.setEnabled(False)
                    self.upload_images_btn.setEnabled(False)
                    self.upload_btn.setEnabled(False)
                    self.upload_zip_btn.setEnabled(False)
                    self.edit_portal_btn.setEnabled(False)
                    self.toggle_status_btn.setEnabled(False)
                    
                    # ファイルリストも非表示
                    self._clear_file_list_table()
                    self.file_list_group.setVisible(False)
                    self.thumbnail_label.setText("ファイルにマウスオーバーで\nプレビューを表示")
                    
                    return
                
                # データポータルにエントリが存在するか確認
                # 公開ページボタンはチェック結果で決定するため一旦無効化
                self.public_view_btn.setEnabled(False)
                self._check_portal_entry_exists(dataset_id)
                
                # ファイルリスト表示を常に更新（既存ファイルがある場合のみ表示）
                if files_exist:
                    self._update_file_list_display(file_list)
                    self.file_list_group.setVisible(True)
                else:
                    # 既存ファイルがない場合はリストをクリアして非表示
                    self._clear_file_list_table()
                    self.file_list_group.setVisible(False)
                    self.thumbnail_label.setText("ファイルにマウスオーバーで\nプレビューを表示")
                    # 画像アップロードボタンも無効化
                    self._update_image_upload_button_state()
                
                # データ取得2タブとの同期（将来実装）
                # self._sync_with_data_fetch2(dataset_id)
                
            else:
                self.dataset_info_label.setText(f"⚠️ JSONファイルが見つかりません: {dataset_id}")
                self._log_status(f"❌ JSONファイル未検出: {dataset_id}", error=True)
                self.upload_btn.setEnabled(False)
                self.bulk_download_btn.setEnabled(False)
                self.open_files_folder_btn.setEnabled(False)
                
        except Exception as e:
            logger.error(f"データセット選択エラー: {e}")
            self._log_status(f"❌ データセット選択エラー: {e}", error=True)
            self.upload_btn.setEnabled(False)
    
    def _on_dataset_selected(self, index: int):
        """シンプル版ドロップダウンからデータセット選択時の処理（フォールバック）"""
        if index < 0:
            return
        
        dataset_data = self.dataset_combo.itemData(index)
        if not dataset_data:
            self.upload_btn.setEnabled(False)
            self._clear_file_list_table()
            self.file_list_group.setVisible(False)
            return
        
        # データセットが変わったらJSONアップロードフラグをリセット
        self.json_uploaded = False
        self.current_t_code = None
        
        dataset_id = dataset_data.get('id')
        dataset_name = dataset_data.get('name', '')
        grant_number = dataset_data.get('grantNumber', '')
        
        # 現在選択中のデータセットIDを保存
        self.current_dataset_id = dataset_id
        
        # JSONファイルパスを探す
        json_path = self._find_dataset_json(dataset_id, grant_number)
        
        if json_path:
            self.selected_json_path = json_path
            self.upload_btn.setEnabled(True)
            
            # データポータルにエントリが存在するか確認
            # 公開ページボタンはチェック結果で決定するため一旦無効化
            self.public_view_btn.setEnabled(False)
            self._check_portal_entry_exists(dataset_id)
            
            # 画像ファイルの取得状況を確認
            files_exist, file_count, file_list = self._check_files_exist(dataset_id)
            
            # ボタンの状態を設定
            self.bulk_download_btn.setEnabled(True)
            
            # 既存ファイルがある場合はチェックマークを表示
            if files_exist:
                self.bulk_download_btn.setText(f"✅ 📥 画像ファイル一括取得 ({file_count}件取得済み)")
                self.open_files_folder_btn.setEnabled(True)
            else:
                self.bulk_download_btn.setText("📥 画像ファイル一括取得")
                # フォルダが存在すればボタンを有効化
                folder_exists = self._check_folder_exists(dataset_id, grant_number)
                self.open_files_folder_btn.setEnabled(folder_exists)
            
            info_text = (
            #    f"データセット: {dataset_name}\n"
                f"ID: {dataset_id}\n"
            #    f"JSONファイル: {Path(json_path).name}\n"
            #    f"画像ファイル: {'取得済み' if files_exist else '未取得'}"
            )
            if files_exist:
                #info_text += f" ({file_count}件)"
                pass
            self.dataset_info_label.setText(info_text)
            self._log_status(f"データセット選択: {dataset_name}")
            
            # 現在選択中のデータセットIDを保存
            self.current_dataset_id = dataset_id
            
            # RDEサイト上にデータセットが存在するか確認
            rde_exists = self._check_rde_dataset_exists(dataset_id)
            
            if not rde_exists:
                # RDEサイトにデータセットが存在しない場合
                self.dataset_info_label.setText(
                    f"⚠️ RDEサイト上にデータセットが存在しません\n"
                    f"データセット: {dataset_name}\n"
                    f"ID: {dataset_id}\n"
                    f"\n※RDEサイトでデータセットを開設してください"
                )
                self._log_status(f"❌ RDEサイト上にデータセットが存在しません: {dataset_id}", error=True)
                
                # 全ボタンを無効化
                self.bulk_download_btn.setEnabled(False)
                self.upload_images_btn.setEnabled(False)
                self.upload_btn.setEnabled(False)
                self.upload_zip_btn.setEnabled(False)
                self.edit_portal_btn.setEnabled(False)
                self.toggle_status_btn.setEnabled(False)
                
                # ファイルリストも非表示
                self._clear_file_list_table()
                self.file_list_group.setVisible(False)
                self.thumbnail_label.setText("ファイルにマウスオーバーで\nプレビューを表示")
                
                return
            
            # ファイルリスト表示を常に更新（既存ファイルがある場合のみ表示）
            if files_exist:
                self._update_file_list_display(file_list)
                self.file_list_group.setVisible(True)
            else:
                # 既存ファイルがない場合はリストをクリアして非表示
                self._clear_file_list_table()
                self.file_list_group.setVisible(False)
                self.thumbnail_label.setText("ファイルにマウスオーバーで\nプレビューを表示")
                # 画像アップロードボタンも無効化
                self._update_image_upload_button_state()
        else:
            self.dataset_info_label.setText(f"⚠️ JSONファイルが見つかりません: {dataset_id}")
            self._log_status(f"❌ JSONファイル未検出: {dataset_id}", error=True)
            self.upload_btn.setEnabled(False)
            self.bulk_download_btn.setEnabled(False)
            self.open_files_folder_btn.setEnabled(False)
            self._clear_file_list_table()
            self.file_list_group.setVisible(False)
            # 画像アップロードボタンも無効化
            self._update_image_upload_button_state()
    
    def _get_dataset_info_from_json(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        """dataset.jsonからデータセット情報を取得"""
        try:
            dataset_json_path = get_dynamic_file_path("output/rde/data/dataset.json")
            
            if not os.path.exists(dataset_json_path):
                return None
            
            with open(dataset_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # データ構造を確認
            datasets = data.get('data', []) if isinstance(data, dict) else data
            
            # dataset_idに一致するデータセットを検索
            for dataset in datasets:
                if isinstance(dataset, dict) and dataset.get('id') == dataset_id:
                    attrs = dataset.get('attributes', {})
                    return {
                        'id': dataset_id,
                        'name': attrs.get('name', ''),
                        'grantNumber': attrs.get('grantNumber', ''),
                        'datasetType': attrs.get('datasetType', ''),
                        'attributes': attrs
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"データセット情報取得エラー: {e}")
            return None
    
    def _save_dataset_json(self, dataset_id: str, grant_number: str, dataset_name: str):
        """
        データセットJSONを保存（データ取得2と同様）
        
        Args:
            dataset_id: データセットID
            grant_number: 課題番号
            dataset_name: データセット名
        """
        try:
            from classes.utils.arim_anonymizer import ARIMAnonymizer
            import shutil
            
            # パス無効文字の置換
            def replace_invalid_path_chars(s):
                if not s:
                    return ""
                table = str.maketrans({
                    '\\': '￥', '/': '／', ':': '：', '*': '＊',
                    '?': '？', '"': '"', '<': '＜', '>': '＞', '|': '｜',
                })
                return s.translate(table)
            
            safe_grant_number = replace_invalid_path_chars(grant_number)
            safe_dataset_name = replace_invalid_path_chars(dataset_name)
            
            # 保存先ディレクトリ
            dataset_dir = get_dynamic_file_path(f"output/rde/data/dataFiles/{safe_grant_number}/{safe_dataset_name}")
            os.makedirs(dataset_dir, exist_ok=True)
            
            # オリジナルのdataset.jsonパス
            original_dataset_json = get_dynamic_file_path(f"output/rde/data/datasets/{dataset_id}.json")
            
            if not os.path.exists(original_dataset_json):
                logger.warning(f"オリジナルのdataset.jsonが見つかりません: {original_dataset_json}")
                return
            
            # dataset.jsonをコピー
            dataset_json_path = os.path.join(dataset_dir, f"{dataset_id}.json")
            shutil.copy2(original_dataset_json, dataset_json_path)
            logger.info(f"dataset.jsonをコピー: {dataset_json_path}")
            self._log_status(f"✅ dataset.json保存完了")
            
            # 匿名化版を作成
            with open(original_dataset_json, 'r', encoding='utf-8') as f:
                dataset_obj = json.load(f)
            
            # ARIMAnonymizerを使用して匿名化
            anonymizer = ARIMAnonymizer(logger=logger)
            
            # 匿名化処理（grantNumberもマスク）
            def anonymize_json(data, grant_num):
                """
                JSONデータを匿名化
                grantNumberは下4桁を除いてマスク（例: JPMXP1223TU0172 -> JPMXP12********）
                """
                # grantNumberのマスク処理
                def mask_grant_number(grant_str):
                    if not grant_str or not isinstance(grant_str, str):
                        return "***"
                    # JPMXP12 までを残して、それ以降を * でマスク
                    if len(grant_str) > 7 and grant_str.startswith("JPMXP"):
                        return grant_str[:7] + "*" * (len(grant_str) - 7)
                    return "***"
                
                if isinstance(data, dict):
                    out = {}
                    for k, v in data.items():
                        kl = k.lower()
                        # attributes特別処理
                        if k == "attributes" and isinstance(v, dict):
                            attrs = v.copy()
                            # grantNumberをマスク
                            if "grantNumber" in attrs:
                                attrs["grantNumber"] = mask_grant_number(attrs["grantNumber"])
                            # その他のフィールドを匿名化
                            if attrs.get("datasetType") == "ANALYSIS":
                                attrs["subjectTitle"] = "*******非開示*******"
                                attrs["name"] = "*******非開示*******"
                            else:
                                for key, val in [("subjectTitle", "*******非開示*******"), ("name", "*******非開示*******")]:
                                    if key in attrs:
                                        attrs[key] = val
                            out[k] = attrs
                        # grantNumber/grant_number/subjectTitle/nameは再帰的に匿名化
                        elif kl in ("grantnumber", "grant_number"):
                            out[k] = mask_grant_number(v) if isinstance(v, str) else "***"
                        elif kl == "subjecttitle":
                            out[k] = "*******非開示*******"
                        elif kl == "name":
                            out[k] = "*******非開示*******"
                        else:
                            out[k] = anonymize_json(v, grant_num)
                    return out
                elif isinstance(data, list):
                    return [anonymize_json(v, grant_num) for v in data]
                return data
            
            anonymized_obj = anonymize_json(dataset_obj, grant_number)
            
            # 匿名化版を保存
            dataset_anonymized_path = os.path.join(dataset_dir, f"{dataset_id}_anonymized.json")
            with open(dataset_anonymized_path, 'w', encoding='utf-8') as f:
                json.dump(anonymized_obj, f, ensure_ascii=False, indent=2)
            
            logger.info(f"匿名化dataset.json保存: {dataset_anonymized_path}")
            self._log_status(f"✅ 匿名化dataset.json保存完了")
            
        except Exception as e:
            logger.error(f"dataset.json保存エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_status(f"⚠️ dataset.json保存エラー: {e}", error=True)
    
    def _check_folder_exists(self, dataset_id: str, grant_number: str = None) -> bool:
        """
        フォルダが存在するか確認
        
        Returns:
            bool: フォルダが存在する場合True
        """
        try:
            if not grant_number:
                dataset_info = self._get_dataset_info_from_json(dataset_id)
                if not dataset_info:
                    return False
                grant_number = dataset_info.get('grantNumber', '不明')
            
            # パス無効文字の置換
            def replace_invalid_path_chars(s):
                if not s:
                    return ""
                table = str.maketrans({
                    '\\': '￥', '/': '／', ':': '：', '*': '＊',
                    '?': '？', '"': '"', '<': '＜', '>': '＞', '|': '｜',
                })
                return s.translate(table)
            
            safe_grant_number = replace_invalid_path_chars(grant_number)
            folder_path = get_dynamic_file_path(f"output/rde/data/dataFiles/{safe_grant_number}")
            
            return os.path.exists(folder_path)
            
        except Exception as e:
            logger.error(f"フォルダ存在確認エラー: {e}")
            return False
    
    def _check_files_exist(self, dataset_id: str) -> tuple:
        """
        ファイルが既にダウンロード済みか確認（データ取得2と同じフォルダ構造）
        
        Returns:
            tuple: (exists: bool, file_count: int, file_list: list)
        """
        try:
            # データセット情報を取得
            dataset_info = self._get_dataset_info_from_json(dataset_id)
            if not dataset_info:
                return False, 0, []
            
            grant_number = dataset_info.get('grantNumber', '不明')
            dataset_name = dataset_info.get('name', 'データセット名未設定')
            
            # パス無効文字の置換
            def replace_invalid_path_chars(s):
                if not s:
                    return ""
                table = str.maketrans({
                    '\\': '￥', '/': '／', ':': '：', '*': '＊',
                    '?': '？', '"': '"', '<': '＜', '>': '＞', '|': '｜',
                })
                return s.translate(table)
            
            safe_grant_number = replace_invalid_path_chars(grant_number)
            safe_dataset_name = replace_invalid_path_chars(dataset_name)
            
            # データ取得2と同じフォルダ構造: output/rde/data/dataFiles/{grantNumber}/{dataset_name}/
            base_dir = get_dynamic_file_path(f"output/rde/data/dataFiles/{safe_grant_number}/{safe_dataset_name}")
            
            if not os.path.exists(base_dir):
                return False, 0, []
            
            # サブフォルダ（タイル単位）を走査
            file_list = []
            for root, dirs, files in os.walk(base_dir):
                for filename in files:
                    if not filename.endswith('.json'):
                        filepath = os.path.join(root, filename)
                        file_list.append({
                            'name': filename,
                            'size': os.path.getsize(filepath),
                            'path': filepath,
                            'relative_path': os.path.relpath(filepath, base_dir)
                        })
            
            return len(file_list) > 0, len(file_list), file_list
            
        except Exception as e:
            logger.error(f"ファイル存在確認エラー: {e}")
            return False, 0, []
    
    def _get_data_ids_from_dataset(self, dataset_id: str) -> list:
        """
        データセットから全てのdata_idを取得
        
        Args:
            dataset_id: データセットID（例: a4865a7a-56c1-42bf-b3f9-d7c75917ec51）
            
        Returns:
            list: data_idのリスト（UUID形式）
        """
        try:
            # dataEntry/{dataset_id}.json から取得（データ取得2と同じパス）
            entry_path = get_dynamic_file_path(f"output/rde/data/dataEntry/{dataset_id}.json")
            
            if not os.path.exists(entry_path):
                logger.warning(f"dataEntryファイルが存在しません: {entry_path}")
                logger.info(f"APIから直接取得を試行します")
                
                # APIから取得
                data_ids = self._fetch_data_ids_from_api(dataset_id)
                return data_ids
            
            # JSONファイルを読み込み
            logger.info(f"dataEntryファイルから読み込み: {entry_path}")
            with open(entry_path, 'r', encoding='utf-8') as f:
                entry_data = json.load(f)
            
            # データ構造を確認して data 配列を取得
            if isinstance(entry_data, dict):
                data_entries = entry_data.get('data', [])
            elif isinstance(entry_data, list):
                data_entries = entry_data
            else:
                logger.error(f"不正なデータ構造: {type(entry_data)}")
                return []
            
            # 各dataエントリからIDを抽出
            data_ids = []
            for entry in data_entries:
                if isinstance(entry, dict):
                    data_id = entry.get('id')
                    if data_id:
                        data_ids.append(data_id)
            
            logger.info(f"データセット {dataset_id} から {len(data_ids)} 件のdata_idを取得")
            return data_ids
            
        except Exception as e:
            logger.error(f"data_id取得エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _fetch_data_ids_from_api(self, dataset_id: str) -> list:
        """
        APIからデータIDリストを取得
        
        Args:
            dataset_id: データセットID
            
        Returns:
            list: data_idのリスト
        """
        try:
            from core.bearer_token_manager import BearerTokenManager
            from classes.utils.api_request_helper import api_request
            
            # Bearer Token取得
            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(self)
            if not bearer_token:
                logger.error("Bearer Tokenが取得できません")
                return []
            
            # APIリクエスト（データ取得2と同じエンドポイント）
            entry_url = f"https://rde-api.nims.go.jp/data?filter%5Bdataset.id%5D={dataset_id}&page%5Blimit%5D=100&page%5Boffset%5D=0"
            headers = {
                "Accept": "application/vnd.api+json",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
                "Authorization": f"Bearer {bearer_token}",
                "Connection": "keep-alive",
                "Host": "rde-api.nims.go.jp",
                "Origin": "https://rde.nims.go.jp",
                "Referer": "https://rde.nims.go.jp/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            }
            
            logger.info(f"APIからデータエントリ取得: {entry_url}")
            resp = api_request("GET", entry_url, headers=headers)
            
            if resp is None or resp.status_code != 200:
                logger.error(f"APIリクエスト失敗: status_code={resp.status_code if resp else 'None'}")
                return []
            
            entry_json = resp.json()
            
            # 取得したデータを保存（次回以降のため）
            entry_path = get_dynamic_file_path(f"output/rde/data/dataEntry/{dataset_id}.json")
            os.makedirs(os.path.dirname(entry_path), exist_ok=True)
            with open(entry_path, "w", encoding="utf-8") as f:
                json.dump(entry_json, f, ensure_ascii=False, indent=2)
            logger.info(f"取得したデータエントリを保存: {entry_path}")
            
            # data配列からIDを抽出
            data_entries = entry_json.get('data', [])
            data_ids = [entry.get('id') for entry in data_entries if isinstance(entry, dict) and entry.get('id')]
            
            logger.info(f"APIから {len(data_ids)} 件のdata_idを取得")
            return data_ids
            
        except Exception as e:
            logger.error(f"API取得エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _find_dataset_json(self, dataset_id: str, grant_number: str = None) -> Optional[str]:
        """データセットIDからJSONファイルを探す"""
        from config.common import get_dynamic_file_path
        
        # JSONファイルはoutput/rde/data/datasets/直下に存在
        datasets_dir = get_dynamic_file_path("output/rde/data/datasets")

        if not os.path.exists(datasets_dir):
            logger.warning(f"データセットディレクトリが存在しません: {datasets_dir}")
            return None
        
        # JSONファイルパスを直接構築
        json_file = f"{dataset_id}.json"
        json_path = os.path.join(datasets_dir, json_file)
        
        if os.path.exists(json_path):
            logger.info(f"JSONファイル発見: {json_path}")
            return json_path
        
        logger.warning(f"JSONファイルが見つかりません: {json_path}")
        return None
    
    def _on_validate_file(self):
        """ファイル検証"""
        if not self.selected_json_path:
            self._show_warning("ファイルが選択されていません")
            return
        
        self._log_status("ファイル検証中...")
        
        try:
            # JSON検証
            with open(self.selected_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            file_size = Path(self.selected_json_path).stat().st_size
            
            self._log_status(
                f"✅ 検証成功\n"
                f"  ファイル: {Path(self.selected_json_path).name}\n"
                f"  サイズ: {file_size:,} bytes\n"
                f"  データ構造: {type(data).__name__}"
            )
            self._show_info("ファイル検証成功")
            
        except json.JSONDecodeError as e:
            self._log_status(f"❌ JSON形式エラー: {e}", error=True)
            self._show_error(f"JSON形式エラー: {e}")
        except Exception as e:
            self._log_status(f"❌ ファイル検証エラー: {e}", error=True)
            self._show_error(f"ファイル検証エラー: {e}")
    
    def _on_upload(self):
        """アップロード実行"""
        if not self.selected_json_path:
            self._show_warning("ファイルが選択されていません")
            return
        
        environment = self.env_combo.currentData()
        if not environment:
            self._show_error("環境が選択されていません")
            return
        
        # 認証情報取得
        credentials = self.auth_manager.get_credentials(environment)
        if not credentials:
            self._show_error(
                f"認証情報が見つかりません\n"
                "「ログイン設定」タブで認証情報を保存してください"
            )
            return

        # テスト環境ではBasic認証が必要（要件）
        if str(environment) == "test":
            if not getattr(credentials, "basic_username", "") or not getattr(credentials, "basic_password", ""):
                self._show_error(
                    "テスト環境ではBasic認証情報が必要です。\n"
                    "『ログイン設定』タブで Basicユーザー/パスワード を保存してください。"
                )
                return
        
        # 匿名化処理
        upload_json_path = self.selected_json_path
        if self.anonymize_checkbox.isChecked():
            self._log_status("匿名化処理中（課題番号をJSONから取得）...")
            upload_json_path = self._anonymize_json(self.selected_json_path)
            if not upload_json_path:
                self._show_error("匿名化処理に失敗しました")
                return
        
        # アップロード確認
        reply = QMessageBox.question(
            self,
            "アップロード確認",
            f"以下の内容でアップロードを実行しますか?\n\n"
            f"環境: {self.env_combo.currentText()}\n"
            f"ファイル: {Path(upload_json_path).name}\n"
            f"匿名化: {'あり' if self.anonymize_checkbox.isChecked() else 'なし'}",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            self._log_status("アップロードをキャンセルしました")
            return
        
        # アップロード実行
        self._execute_upload(environment, credentials, upload_json_path)
    
    def _anonymize_json(self, json_path: str) -> Optional[str]:
        """
        JSON匿名化（既存のARIMAnonymizer実装に準拠）
        課題番号はJSONから自動取得
        
        Args:
            json_path: 元JSONファイルパス
            
        Returns:
            str: 匿名化後のファイルパス（匿名化不要の場合は元のパス）
        """
        try:
            from classes.utils.arim_anonymizer import ARIMAnonymizer
            anonymizer = ARIMAnonymizer(logger=logger)
            
            # JSONファイルを読み込み
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 課題番号をJSONから取得
            grant_number = None
            if isinstance(data, dict):
                # data.attributes.grantNumber を探す
                if "data" in data and isinstance(data["data"], dict):
                    attrs = data["data"].get("attributes", {})
                    grant_number = attrs.get("grantNumber")
                # トップレベルのattributesも確認
                if not grant_number and "attributes" in data:
                    grant_number = data["attributes"].get("grantNumber")
            
            if not grant_number:
                logger.warning(f"[ARIM] 課題番号がJSONから取得できません: {json_path}")
                grant_number = "UNKNOWN"
            
            logger.info(f"[ARIM] 課題番号を取得: {grant_number}")
            self._log_status(f"課題番号: {grant_number}")
            
            # 匿名化前のデータをコピー（差分比較用）
            before_json = json.dumps(data, ensure_ascii=False, indent=2)
            
            # 匿名化実行（dataが直接変更される）
            changed = anonymizer.anonymize_json(data, grant_number)
            
            if not changed:
                # 匿名化不要の場合は元のファイルをそのまま使用
                self._log_status("ℹ️ 匿名化対象フィールドなし（元ファイルを使用）")
                logger.info(f"[ARIM] 匿名化不要: {json_path}")
                return json_path
            
            # 匿名化後のデータ
            after_json = json.dumps(data, ensure_ascii=False, indent=2)
            
            # 匿名化後のファイルパス（非開示_プレフィックス）
            anon_path = str(Path(json_path).parent / f"非開示_{Path(json_path).name}")
            
            # 匿名化後ファイルを保存
            with open(anon_path, 'w', encoding='utf-8') as f:
                f.write(after_json)
            
            # 差分ファイルを保存（デバッグ用）
            diff_path = str(Path(json_path).parent / f"差分_{Path(json_path).stem}.txt")
            import difflib
            diff = difflib.unified_diff(
                before_json.splitlines(keepends=True),
                after_json.splitlines(keepends=True),
                fromfile=Path(json_path).name,
                tofile=f"非開示_{Path(json_path).name}"
            )
            with open(diff_path, 'w', encoding='utf-8') as f:
                f.writelines(diff)
            
            self._log_status(f"✅ 匿名化完了: {Path(anon_path).name}")
            logger.info(f"[ARIM] 匿名化済: {anon_path}")
            logger.info(f"[ARIM] 差分: {diff_path}")
            
            return anon_path
            
        except Exception as e:
            logger.error(f"匿名化エラー: {e}")
            self._log_status(f"❌ 匿名化エラー: {e}", error=True)
            return None
    
    def _execute_upload(self, environment: str, credentials, json_path: str):
        """アップロード実行"""
        try:
            self._log_status("=" * 50)
            self._log_status("📤 アップロード開始")
            self._log_status("=" * 50)
            
            # UIを無効化
            self.upload_btn.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # インデターミネート
            
            # クライアント作成
            from ..core.portal_client import PortalClient
            from ..core.uploader import Uploader
            self.portal_client = PortalClient(environment)
            self.portal_client.set_credentials(credentials)
            
            # アップローダー作成
            self.uploader = Uploader(self.portal_client)
            
            # ワーカースレッドで実行
            self.upload_worker = UploadWorker(self.uploader, json_path)
            self.upload_worker.progress.connect(self._log_status)
            self.upload_worker.finished.connect(self._on_upload_finished)
            self.upload_worker.start()
            
        except Exception as e:
            logger.error(f"アップロード実行エラー: {e}")
            self._log_status(f"❌ アップロード実行エラー: {e}", error=True)
            self._show_error(f"アップロード実行エラー: {e}")
            self.upload_btn.setEnabled(True)
            self.progress_bar.setVisible(False)
    
    def _on_upload_finished(self, success: bool, message: str):
        """アップロード完了"""
        self.progress_bar.setVisible(False)
        self.upload_btn.setEnabled(True)
        
        if success:
            self._log_status("=" * 50)
            self._log_status(f"✅ アップロード成功: {message}")
            self._log_status("=" * 50)
            self._show_info(f"アップロード成功\n{message}\n\n画像ファイルをアップロードする場合は、\n「画像アップロード」ボタンをご利用ください。")
            
            # JSONアップロード完了フラグを設定
            self.json_uploaded = True
            
            # 画像アップロードボタンの有効化判定を更新
            self._update_image_upload_button_state()
            
            # データポータル修正ボタンを有効化（データセットが選択されている場合）
            if self.current_dataset_id:
                self.edit_portal_btn.setEnabled(True)
                logger.info(f"データポータル修正ボタン有効化: dataset_id={self.current_dataset_id}")

            # ZIPアップロードボタンの有効化判定を更新
            self._update_zip_upload_button_state()
            
        else:
            self._log_status("=" * 50)
            self._log_status(f"❌ アップロード失敗: {message}", error=True)
            self._log_status("=" * 50)
            self._show_error(f"アップロード失敗\n{message}")
        
        self.upload_completed.emit(success, message)

    def _on_upload_zip(self) -> None:
        """コンテンツZIPアップロードの起点"""
        if not self.current_dataset_id:
            self._show_warning("データセットが選択されていません")
            return

        if not self.edit_portal_btn.isEnabled():
            self._show_warning("データカタログ修正が有効なデータセットのみ実行できます")
            return

        environment = self.env_combo.currentData()
        if not environment:
            self._show_error("環境が選択されていません")
            return

        credentials = self.auth_manager.get_credentials(environment)
        if not credentials:
            self._show_error(
                f"認証情報が見つかりません\n"
                "「ログイン設定」タブで認証情報を保存してください"
            )
            return

        # テスト環境ではBasic認証が必要（要件）
        if str(environment) == "test":
            if not getattr(credentials, "basic_username", "") or not getattr(credentials, "basic_password", ""):
                self._show_error(
                    "テスト環境ではBasic認証情報が必要です。\n"
                    "『ログイン設定』タブで Basicユーザー/パスワード を保存してください。"
                )
                return

        # t_code を取得（選択データセットから導出）
        self._log_status("t_codeを取得中...")
        t_code = self._get_t_code_for_dataset(self.current_dataset_id)
        if not t_code:
            self._show_error(f"データセットID {self.current_dataset_id} に対応するt_codeが見つかりません")
            return

        # ボタン統合: ローカルZIPか自動作成かを選択
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("コンテンツZIPアップロード")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(
            "コンテンツZIPのアップロード方法を選択してください。\n\n"
            "ローカルZIP: 手元のZIPファイルをアップロード\n"
            "自動作成: RDEから取得してZIP化し、そのZIPをアップロード"
        )
        local_btn = msg_box.addButton("ローカルZIPを選択", QMessageBox.YesRole)
        auto_btn = msg_box.addButton("RDEから取得してZIP自動作成", QMessageBox.NoRole)
        cancel_btn = msg_box.addButton("キャンセル", QMessageBox.RejectRole)
        msg_box.setDefaultButton(local_btn)
        msg_box.exec()

        clicked = msg_box.clickedButton()
        if clicked == cancel_btn:
            self._log_status("ZIPアップロードをキャンセルしました")
            return
        if clicked == auto_btn:
            # 既存の自動作成フローへ
            self._on_upload_zip_auto()
            return

        zip_path, _ = QFileDialog.getOpenFileName(
            self,
            "コンテンツZIPを選択",
            get_dynamic_file_path("output"),
            "ZIP Files (*.zip);;All Files (*)",
        )
        if not zip_path:
            return

        # ZIP形式のみ許可
        from ..core.uploader import Uploader
        ok, msg = Uploader.is_zip_file(zip_path)
        if not ok:
            self._show_error(msg)
            return

        self.selected_zip_path = zip_path

        reply = QMessageBox.question(
            self,
            "ZIPアップロード確認",
            "以下の内容でコンテンツZIPをアップロードしますか?\n\n"
            f"環境: {self.env_combo.currentText()}\n"
            f"データセットID: {self.current_dataset_id}\n"
            f"t_code: {t_code}\n"
            f"ファイル: {Path(zip_path).name}\n\n"
            "※既存ファイルがある場合、上書きされる可能性があります",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self._log_status("ZIPアップロードをキャンセルしました")
            return

        self._execute_zip_upload(environment, credentials, t_code, zip_path)

    def _on_upload_zip_auto(self) -> None:
        """コンテンツZIPを自動作成してアップロードする"""
        if not self.current_dataset_id:
            self._show_warning("データセットが選択されていません")
            return

        if not self.edit_portal_btn.isEnabled():
            self._show_warning("データカタログ修正が有効なデータセットのみ実行できます")
            return

        environment = self.env_combo.currentData()
        if not environment:
            self._show_error("環境が選択されていません")
            return

        credentials = self.auth_manager.get_credentials(environment)
        if not credentials:
            self._show_error(
                "認証情報が見つかりません\n"
                "『ログイン設定』タブで認証情報を保存してください"
            )
            return

        # テスト環境ではBasic認証が必要（要件）
        if str(environment) == "test":
            if not getattr(credentials, "basic_username", "") or not getattr(credentials, "basic_password", ""):
                self._show_error(
                    "テスト環境ではBasic認証情報が必要です。\n"
                    "『ログイン設定』タブで Basicユーザー/パスワード を保存してください。"
                )
                return

        # t_code を取得（選択データセットから導出）
        self._log_status("t_codeを取得中...")
        t_code = self._get_t_code_for_dataset(self.current_dataset_id)
        if not t_code:
            self._show_error(f"データセットID {self.current_dataset_id} に対応するt_codeが見つかりません")
            return

        try:
            from core.bearer_token_manager import BearerTokenManager
            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(self)
            if not bearer_token:
                self._show_error("Bearer Tokenが取得できません。ログインを確認してください。")
                return

            dataset_info = self._get_dataset_info_from_json(self.current_dataset_id)
            if not dataset_info:
                self._show_error(f"データセット情報が取得できません: {self.current_dataset_id}")
                return

            dataset_name = dataset_info.get('name', 'データセット名未設定')
            grant_number = dataset_info.get('grantNumber', '不明')

            data_ids = self._get_data_ids_from_dataset(self.current_dataset_id)
            if not data_ids:
                self._show_error(f"データセットに含まれるデータが見つかりません: {self.current_dataset_id}")
                return

            # dataEntry から tile 情報を引く（ベストエフォート）
            tile_map = {}
            try:
                entry_path = get_dynamic_file_path(f"output/rde/data/dataEntry/{self.current_dataset_id}.json")
                if os.path.exists(entry_path):
                    with open(entry_path, 'r', encoding='utf-8') as f:
                        entry_json = json.load(f)
                    for entry in entry_json.get('data', []) or []:
                        did = entry.get('id')
                        attrs = entry.get('attributes', {}) or {}
                        if did:
                            tile_map[str(did)] = (
                                str(attrs.get('name', '')),
                                str(attrs.get('dataNumber', '0')),
                            )
            except Exception:
                tile_map = {}

            from qt_compat.widgets import QProgressDialog, QApplication
            from qt_compat.core import Qt

            progress = QProgressDialog("ファイル一覧を取得中...", "キャンセル", 0, len(data_ids), self)
            progress.setWindowTitle("ZIP自動作成")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.show()
            QApplication.processEvents()

            from classes.utils.api_request_helper import api_request
            from classes.data_fetch2.core.logic.fetch2_filelist_logic import replace_invalid_path_chars
            from classes.data_portal.core.contents_zip_auto import filter_file_entries_excluding_nonshared_raw
            from .contents_zip_builder_dialog import ContentsZipBuilderDialog, ContentsZipCandidate
            from qt_compat.widgets import QDialog

            safe_dataset_name = replace_invalid_path_chars(dataset_name)
            safe_grant_number = replace_invalid_path_chars(grant_number)
            save_dir_base = get_dynamic_file_path("output/rde/data/dataFiles")

            candidates = []

            def _expected_local_path(tile_name: str, tile_number: str, file_name: str) -> str:
                safe_tile_name = replace_invalid_path_chars(tile_name or "unknown_tile")
                safe_tile_number = (str(tile_number or "0").strip() or "0")
                tile_dir = f"{safe_tile_number}_{safe_tile_name}".strip('_')
                return os.path.join(save_dir_base, str(safe_grant_number), str(safe_dataset_name), tile_dir, str(file_name))

            for i, data_id in enumerate(data_ids):
                if progress.wasCanceled():
                    self._log_status("ファイル一覧取得をキャンセルしました")
                    return
                progress.setValue(i)
                progress.setLabelText(f"ファイル一覧取得中... ({i+1}/{len(data_ids)})\nデータID: {str(data_id)[:8]}...")
                QApplication.processEvents()

                files_json_path = os.path.join(OUTPUT_DIR, f"rde/data/dataFiles/sub/{data_id}.json")
                files_data = None
                try:
                    if os.path.exists(files_json_path):
                        with open(files_json_path, 'r', encoding='utf-8') as f:
                            files_data = json.load(f)
                    else:
                        headers = {
                            "Accept": "application/vnd.api+json",
                            "Authorization": f"Bearer {bearer_token}",
                        }
                        # まずは fileType フィルタなしで取得（全タイプ対象）
                        files_url = (
                            f"https://rde-api.nims.go.jp/data/{data_id}/files"
                            "?page%5Blimit%5D=100"
                            "&page%5Boffset%5D=0"
                        )
                        resp = api_request("GET", files_url, headers=headers)
                        if resp and resp.status_code == 200:
                            files_data = resp.json()
                        else:
                            # フォールバック（従来のフィルタ付きURL）
                            files_url = (
                                f"https://rde-api.nims.go.jp/data/{data_id}/files"
                                "?page%5Blimit%5D=100"
                                "&page%5Boffset%5D=0"
                                "&filter%5BfileType%5D%5B%5D=META"
                                "&filter%5BfileType%5D%5B%5D=MAIN_IMAGE"
                                "&filter%5BfileType%5D%5B%5D=OTHER_IMAGE"
                                "&filter%5BfileType%5D%5B%5D=NONSHARED_RAW"
                                "&filter%5BfileType%5D%5B%5D=RAW"
                                "&filter%5BfileType%5D%5B%5D=STRUCTURED"
                                "&fileTypeOrder=RAW%2CNONSHARED_RAW%2CMETA%2CSTRUCTURED%2CMAIN_IMAGE%2COTHER_IMAGE"
                            )
                            resp2 = api_request("GET", files_url, headers=headers)
                            if resp2 and resp2.status_code == 200:
                                files_data = resp2.json()
                            else:
                                continue

                        if files_data is not None:
                            os.makedirs(os.path.dirname(files_json_path), exist_ok=True)
                            with open(files_json_path, 'w', encoding='utf-8') as f:
                                json.dump(files_data, f, ensure_ascii=False, indent=2)

                    file_entries = (files_data or {}).get('data', [])
                    filtered = filter_file_entries_excluding_nonshared_raw(file_entries)

                    tile_name, tile_number = tile_map.get(str(data_id), ("", "0"))

                    for entry in filtered:
                        attrs = entry.get('attributes', {}) or {}
                        file_id = str(entry.get('id') or "")
                        file_name = str(attrs.get('fileName') or "")
                        file_type = str(attrs.get('fileType') or "UNKNOWN")
                        file_size = int(attrs.get('fileSize') or 0)
                        if not (file_id and file_name):
                            continue

                        local_path = _expected_local_path(tile_name, tile_number, file_name)
                        candidates.append(
                            ContentsZipCandidate(
                                checked=True,
                                file_id=file_id,
                                file_name=file_name,
                                file_type=file_type,
                                file_size=file_size,
                                data_entry_id=str(data_id),
                                tile_name=tile_name,
                                tile_number=str(tile_number or "0"),
                                local_path=local_path,
                                exists_locally=os.path.exists(local_path),
                            )
                        )
                except Exception:
                    continue

            progress.setValue(len(data_ids))
            progress.close()

            if not candidates:
                self._show_warning("対象ファイルが見つかりませんでした")
                return

            dialog = ContentsZipBuilderDialog(self, candidates)
            if dialog.exec() != QDialog.Accepted:
                self._log_status("ZIP自動作成をキャンセルしました")
                return

            selected = dialog.get_selected()
            if not selected:
                self._show_warning("ZIPに含めるファイルが選択されていません")
                return

            from classes.data_portal.core.contents_zip_auto import SelectedFile, compute_filetype_summary, format_bytes
            selected_files = [
                SelectedFile(
                    file_id=c.file_id,
                    file_name=c.file_name,
                    file_type=c.file_type,
                    file_size=c.file_size,
                    local_path=c.local_path,
                )
                for c in selected
            ]
            summary = compute_filetype_summary(selected_files)
            total_size = sum(v[1] for v in summary.values())
            existing_count = sum(1 for c in selected if c.exists_locally)
            summary_lines = [
                f"- {ft}: {cnt}件 / {format_bytes(sz)}" for ft, (cnt, sz) in sorted(summary.items())
            ]
            summary_text = "\n".join(summary_lines)

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("ZIP自動作成 確認")
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setText(
                "選択ファイルをダウンロードしてZIP化し、アップロードします。\n\n"
                f"データセットID: {self.current_dataset_id}\n"
                f"t_code: {t_code}\n"
                f"選択: {len(selected)}件 / 合計: {format_bytes(total_size)}\n"
                f"既存ファイル: {existing_count}件\n\n"
                "種類別:\n"
                f"{summary_text}\n\n"
                "既存ファイルがある場合の扱いを選択してください。"
            )

            use_existing_btn = msg_box.addButton("既存は再取得しない", QMessageBox.YesRole)
            overwrite_btn = msg_box.addButton("上書きダウンロード", QMessageBox.NoRole)
            cancel_btn = msg_box.addButton("キャンセル", QMessageBox.RejectRole)
            msg_box.setDefaultButton(use_existing_btn)
            msg_box.exec()

            clicked = msg_box.clickedButton()
            if clicked == cancel_btn:
                self._log_status("ZIP自動作成をキャンセルしました")
                return
            overwrite = clicked == overwrite_btn

            # ダウンロード
            from classes.data_fetch2.core.logic.fetch2_filelist_logic import download_file_for_data_id

            dl_progress = QProgressDialog("ファイルをダウンロード中...", "キャンセル", 0, len(selected), self)
            dl_progress.setWindowTitle("ZIP自動作成")
            dl_progress.setWindowModality(Qt.WindowModal)
            dl_progress.setMinimumDuration(0)
            dl_progress.show()
            QApplication.processEvents()

            downloaded = []
            for idx, c in enumerate(selected):
                if dl_progress.wasCanceled():
                    self._log_status("ダウンロードをキャンセルしました")
                    return
                dl_progress.setValue(idx)
                dl_progress.setLabelText(f"{idx+1}/{len(selected)}: {c.file_name}")
                QApplication.processEvents()

                expected_path = c.local_path
                if (not overwrite) and expected_path and os.path.exists(expected_path):
                    downloaded.append(
                        SelectedFile(
                            file_id=c.file_id,
                            file_name=c.file_name,
                            file_type=c.file_type,
                            file_size=c.file_size,
                            local_path=expected_path,
                        )
                    )
                    continue

                save_path = download_file_for_data_id(
                    data_id=c.file_id,
                    bearer_token=bearer_token,
                    save_dir_base=save_dir_base,
                    file_name=c.file_name,
                    grantNumber=safe_grant_number,
                    dataset_name=safe_dataset_name,
                    tile_name=c.tile_name,
                    tile_number=c.tile_number,
                    parent=self,
                )
                if save_path:
                    downloaded.append(
                        SelectedFile(
                            file_id=c.file_id,
                            file_name=c.file_name,
                            file_type=c.file_type,
                            file_size=c.file_size,
                            local_path=str(save_path),
                        )
                    )

            dl_progress.setValue(len(selected))
            dl_progress.close()

            if not downloaded:
                self._show_warning("ダウンロードできたファイルがありません")
                return

            # ZIP作成（dataFiles/{grant}/{dataset}/.ZIP 配下）
            from datetime import datetime
            from classes.data_portal.core.contents_zip_auto import build_zip

            zip_dir = get_dynamic_file_path(
                f"output/rde/data/dataFiles/{safe_grant_number}/{safe_dataset_name}/.ZIP"
            )
            os.makedirs(zip_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_path = os.path.join(zip_dir, f"{self.current_dataset_id}_{timestamp}.zip")
            base_dir = get_dynamic_file_path(
                f"output/rde/data/dataFiles/{safe_grant_number}/{safe_dataset_name}"
            )
            zip_path = build_zip(zip_path=zip_path, base_dir=base_dir, files=downloaded)
            self._log_status(f"✅ ZIP作成完了: {Path(zip_path).name}")

            # そのままアップロード
            self._execute_zip_upload(environment, credentials, t_code, zip_path)

        except Exception as e:
            logger.error(f"ZIP自動作成アップロードエラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._show_error(f"ZIP自動作成アップロードでエラーが発生しました\n{e}")

    def _execute_zip_upload(self, environment: str, credentials, t_code: str, zip_path: str) -> None:
        try:
            self._log_status("=" * 50)
            self._log_status("📦 コンテンツZIPアップロード開始")
            self._log_status("=" * 50)

            # UIを無効化
            self.upload_zip_btn.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)

            # クライアント/アップローダー作成
            from ..core.portal_client import PortalClient
            from ..core.uploader import Uploader

            self.portal_client = PortalClient(environment)
            self.portal_client.set_credentials(credentials)
            self.uploader = Uploader(self.portal_client)

            self.contents_zip_upload_worker = ContentsZipUploadWorker(self.uploader, t_code, zip_path)
            self.contents_zip_upload_worker.progress.connect(self._log_status)
            self.contents_zip_upload_worker.finished.connect(self._on_upload_zip_finished)
            self.contents_zip_upload_worker.start()

        except Exception as e:
            logger.error(f"ZIPアップロード実行エラー: {e}")
            self._log_status(f"❌ ZIPアップロード実行エラー: {e}", error=True)
            self._show_error(f"ZIPアップロード実行エラー: {e}")
            self.progress_bar.setVisible(False)
            self._update_zip_upload_button_state()

    def _on_upload_zip_finished(self, success: bool, message: str) -> None:
        self.progress_bar.setVisible(False)
        self._update_zip_upload_button_state()

        if success:
            self._log_status("=" * 50)
            self._log_status(f"✅ ZIPアップロード成功: {message}")
            self._log_status("=" * 50)
            self._show_info(f"ZIPアップロード成功\n{message}")

            # コンテンツリンク（アップ済み）表示を更新
            try:
                if self.current_dataset_id:
                    self._check_portal_entry_exists(self.current_dataset_id)
            except Exception:
                pass
        else:
            self._log_status("=" * 50)
            self._log_status(f"❌ ZIPアップロード失敗: {message}", error=True)
            self._log_status("=" * 50)
            self._show_error(f"ZIPアップロード失敗\n{message}")
    
    def _log_status(self, message: str, error: bool = False):
        """ステータスログ"""
        # NOTE:
        # 以前はメッセージごとにHTMLで色を埋め込んでいたため、
        # テーマ切替後も既存文字列の色が残り、背景色だけが変わって視認性が悪化していた。
        # ここでは「テキストエリア全体のforeground/background」をstyleSheetで管理し、
        # メッセージ単位での色指定は行わない。
        try:
            from qt_compat.gui import QTextCursor

            cursor = self.status_text.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(f"{message}\n")
            self.status_text.setTextCursor(cursor)
        except Exception:
            # Fallback
            try:
                self.status_text.append(message)
            except Exception:
                pass

        if error:
            logger.error(message)
        else:
            logger.info(message)
    
    def _show_info(self, message: str):
        """情報メッセージ"""
        QMessageBox.information(self, "情報", message)
    
    def _show_warning(self, message: str):
        """警告メッセージ"""
        QMessageBox.warning(self, "警告", message)
    
    def _show_error(self, message: str):
        """エラーメッセージ"""
        QMessageBox.critical(self, "エラー", message)
    
    def _on_bulk_download(self):
        """画像ファイル一括取得（データ取得2と同じフォルダ構造）"""
        if not self.current_dataset_id:
            self._show_warning("データセットが選択されていません")
            return
        
        dataset_id = self.current_dataset_id
        
        # データセット情報を取得
        dataset_info = self._get_dataset_info_from_json(dataset_id)
        if not dataset_info:
            self._show_error(f"データセット情報が取得できません: {dataset_id}")
            return
        
        dataset_name = dataset_info.get('name', 'データセット名未設定')
        grant_number = dataset_info.get('grantNumber', '不明')
        
        # 既存ファイルチェック
        files_exist, file_count, file_list = self._check_files_exist(dataset_id)
        
        # 既存ファイルがある場合は確認ダイアログを表示
        if files_exist:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("既存ファイル確認")
            msg_box.setText(
                f"このデータセットには既に {file_count} 件のファイルが取得済みです。\n\n"
                f"データセット: {dataset_name}\n"
                f"保存先: output/rde/data/dataFiles/{grant_number}/\n\n"
                "どの操作を行いますか？"
            )
            msg_box.setIcon(QMessageBox.Question)
            
            # カスタムボタン
            use_existing_btn = msg_box.addButton("既存ファイルを使用", QMessageBox.YesRole)
            re_download_btn = msg_box.addButton("再取得", QMessageBox.NoRole)
            cancel_btn = msg_box.addButton("キャンセル", QMessageBox.RejectRole)
            
            msg_box.setDefaultButton(use_existing_btn)
            msg_box.exec()
            
            clicked_button = msg_box.clickedButton()
            
            if clicked_button == use_existing_btn:
                # 既存ファイルを使用（ダウンロードせずにファイルリスト表示）
                self._log_status(f"既存ファイルを使用します ({file_count}件)")
                self._update_file_list_display(file_list)
                self.open_files_folder_btn.setEnabled(True)
                return
            elif clicked_button == cancel_btn:
                # キャンセル
                self._log_status("操作をキャンセルしました")
                return
            # re_download_btn の場合は処理を継続
        
        # 確認ダイアログ
        reply = QMessageBox.question(
            self,
            "画像ファイル一括取得",
            f"データセットID: {dataset_id}\n\n"
            "このデータセットに含まれる画像ファイルを一括取得しますか？\n"
            "（データ取得2と同じフォルダに保存されます）",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        try:
            # Bearer Token取得
            from core.bearer_token_manager import BearerTokenManager
            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(self)
            
            if not bearer_token:
                self._show_error("Bearer Tokenが取得できません。ログインを確認してください。")
                return
            
            self._log_status(f"画像ファイル一括取得開始: {dataset_id}")
            
            # データセット情報を取得
            dataset_info = self._get_dataset_info_from_json(dataset_id)
            if not dataset_info:
                self._show_error(f"データセット情報が取得できません: {dataset_id}")
                return
            
            dataset_name = dataset_info.get('name', 'データセット名未設定')
            grant_number = dataset_info.get('grantNumber', '不明')
            
            # データセットJSONを保存（データ取得2と同様）
            self._save_dataset_json(dataset_id, grant_number, dataset_name)
            
            # データエントリを取得
            data_ids = self._get_data_ids_from_dataset(dataset_id)
            
            if not data_ids:
                self._show_error(f"データセットに含まれるデータが見つかりません: {dataset_id}")
                self._log_status(f"❌ データID取得失敗: {dataset_id}", error=True)
                return
            
            # プログレスダイアログ表示
            from qt_compat.widgets import QProgressDialog, QApplication
            from qt_compat.core import Qt
            
            progress = QProgressDialog(
                f"準備中...", 
                "キャンセル", 
                0, 
                100,  # パーセント表示
                self
            )
            progress.setWindowModality(Qt.WindowModal)
            progress.setWindowTitle("画像ファイル取得")
            progress.setMinimumDuration(0)  # 即座に表示
            progress.show()
            QApplication.processEvents()  # UI更新
            
            # データ取得2のロジックを使用して各data_idのファイルをダウンロード
            from classes.data_fetch2.core.logic.fetch2_filelist_logic import download_file_for_data_id
            from classes.utils.api_request_helper import api_request
            from config.common import OUTPUT_DIR
            
            # パス無効文字の置換関数
            def replace_invalid_path_chars(s):
                if not s:
                    return ""
                table = str.maketrans({
                    '\\': '￥', '/': '／', ':': '：', '*': '＊',
                    '?': '？', '"': '"', '<': '＜', '>': '＞', '|': '｜',
                })
                return s.translate(table)
            
            safe_dataset_name = replace_invalid_path_chars(dataset_name)
            safe_grant_number = replace_invalid_path_chars(grant_number)
            save_dir_base = os.path.join(OUTPUT_DIR, "rde", "data", "dataFiles")
            
            success_count = 0
            total_files = 0
            
            for i, data_id in enumerate(data_ids):
                if progress.wasCanceled():
                    self._log_status(f"ダウンロードキャンセル: {i}/{len(data_ids)}")
                    break
                
                # 基本進捗（データ単位）
                base_progress = int((i / len(data_ids)) * 100)
                
                progress.setLabelText(f"ファイル情報取得中... ({i+1}/{len(data_ids)})\nデータID: {data_id[:8]}...")
                progress.setValue(base_progress)
                QApplication.processEvents()
                
                try:
                    # Step 1: ファイル一覧JSONを取得（存在しない場合のみ）
                    files_json_path = os.path.join(OUTPUT_DIR, f"rde/data/dataFiles/sub/{data_id}.json")
                    
                    if not os.path.exists(files_json_path):
                        # APIからファイル一覧を取得
                        files_url = (
                            f"https://rde-api.nims.go.jp/data/{data_id}/files"
                            "?page%5Blimit%5D=100"
                            "&page%5Boffset%5D=0"
                            "&filter%5BfileType%5D%5B%5D=META"
                            "&filter%5BfileType%5D%5B%5D=MAIN_IMAGE"
                            "&filter%5BfileType%5D%5B%5D=OTHER_IMAGE"
                            "&filter%5BfileType%5D%5B%5D=NONSHARED_RAW"
                            "&filter%5BfileType%5D%5B%5D=RAW"
                            "&filter%5BfileType%5D%5B%5D=STRUCTURED"
                            "&fileTypeOrder=RAW%2CNONSHARED_RAW%2CMETA%2CSTRUCTURED%2CMAIN_IMAGE%2COTHER_IMAGE"
                        )
                        headers = {
                            "Accept": "application/vnd.api+json",
                            "Authorization": f"Bearer {bearer_token}",
                        }
                        
                        resp = api_request("GET", files_url, headers=headers)
                        
                        if resp and resp.status_code == 200:
                            files_data = resp.json()
                            os.makedirs(os.path.dirname(files_json_path), exist_ok=True)
                            with open(files_json_path, "w", encoding="utf-8") as f:
                                json.dump(files_data, f, ensure_ascii=False, indent=2)
                            logger.info(f"ファイル一覧JSON保存: {files_json_path}")
                        else:
                            logger.warning(f"ファイル一覧取得失敗 (data_id: {data_id}): HTTP {resp.status_code if resp else 'None'}")
                            continue
                    
                    # files_dataを読み込み
                    with open(files_json_path, 'r', encoding='utf-8') as f:
                        files_data = json.load(f)
                    
                    # data配列から画像ファイルを抽出
                    file_entries = files_data.get("data", [])
                    
                    # 画像ファイル（JPG/PNG）のみを抽出し、ベース名で重複を排除
                    image_entries = []
                    seen_basenames = set()
                    skipped_count = 0
                    
                    for entry in file_entries:
                        attrs = entry.get("attributes", {})
                        fname = attrs.get("fileName")
                        if fname:
                            fext = os.path.splitext(fname)[1].lower()
                            if fext in ['.jpg', '.jpeg', '.png']:
                                # ベース名（拡張子を除く）を取得
                                basename = os.path.splitext(fname)[0]
                                # 重複チェック: 同じベース名のファイルは1回だけダウンロード
                                if basename not in seen_basenames:
                                    seen_basenames.add(basename)
                                    image_entries.append(entry)
                                    logger.debug(f"画像ファイル登録: {fname} (basename: {basename})")
                                else:
                                    skipped_count += 1
                                    logger.debug(f"重複スキップ: {fname} (basename: {basename} は既に登録済み)")
                    
                    if skipped_count > 0:
                        logger.info(f"重複除外: {skipped_count}件のファイルをスキップしました")
                    
                    # タイル情報を取得（dataEntry APIから）
                    entry_path = os.path.join(OUTPUT_DIR, f"rde/data/dataEntry/{dataset_id}.json")
                    tile_name = "unknown_tile"
                    tile_number = "0"
                    
                    if os.path.exists(entry_path):
                        with open(entry_path, 'r', encoding='utf-8') as f:
                            entry_json = json.load(f)
                        
                        # data配列から該当data_idの情報を検索
                        for entry in entry_json.get('data', []):
                            if entry.get('id') == data_id:
                                attrs = entry.get('attributes', {})
                                tile_name = attrs.get('name', 'unknown_tile')
                                tile_number = str(attrs.get('dataNumber', '0'))
                                break
                    
                    # Step 2: 各ファイルをダウンロード（データ取得2のロジックを使用）
                    for idx, file_entry in enumerate(image_entries):
                        file_id = file_entry.get("id")
                        attributes = file_entry.get("attributes", {})
                        file_name = attributes.get("fileName")
                        
                        if not file_id or not file_name:
                            continue
                        
                        # プログレス更新
                        file_progress = int(((i + (idx / len(image_entries))) / len(data_ids)) * 100)
                        progress.setValue(file_progress)
                        progress.setLabelText(
                            f"データ {i+1}/{len(data_ids)}: {file_name}\n"
                            f"ファイル {idx+1}/{len(image_entries)} (全体 {file_progress}%)"
                        )
                        QApplication.processEvents()
                        
                        # download_file_for_data_idを使用（データ取得2と同じ保存構造）
                        result = download_file_for_data_id(
                            data_id=file_id,
                            bearer_token=bearer_token,
                            save_dir_base=save_dir_base,
                            file_name=file_name,
                            grantNumber=safe_grant_number,
                            dataset_name=safe_dataset_name,
                            tile_name=replace_invalid_path_chars(tile_name),
                            tile_number=tile_number,
                            parent=self
                        )
                        
                        if result:
                            total_files += 1
                            self._log_status(f"[{i+1}/{len(data_ids)}] ダウンロード完了: {file_name}")
                    
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"データID {data_id} のダウンロード失敗: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    self._log_status(f"⚠️ データID {data_id[:8]}... のダウンロード失敗", error=True)
            
            progress.setValue(100)
            progress.close()
            
            if total_files > 0:
                self._log_status(f"✅ 画像ファイル取得完了: {total_files}件（{success_count}/{len(data_ids)}データ）")
                
                # ボタンの状態を更新
                self.bulk_download_btn.setEnabled(False)
                self.open_files_folder_btn.setEnabled(True)
                
                # 情報ラベルを更新
                json_path = self._find_dataset_json(dataset_id, grant_number)
                
                info_text = (
                    f"データセット: {dataset_name}\n"
                    f"ID: {dataset_id}\n"
                    f"JSONファイル: {Path(json_path).name if json_path else 'なし'}\n"
                    f"画像ファイル: 取得済み ({total_files}件)"
                )
                self.dataset_info_label.setText(info_text)
                
                # ファイルリスト表示を更新
                _, _, file_list = self._check_files_exist(dataset_id)
                self._update_file_list_display(file_list)
                
                self._show_info(f"画像ファイルの取得が完了しました\n\n取得ファイル数: {total_files}件\n処理データ数: {success_count}/{len(data_ids)}")
            else:
                self._log_status(f"⚠️ 画像ファイルが取得されませんでした", error=True)
                self._show_warning("画像ファイルが取得されませんでした")
            
        except ImportError as e:
            logger.error(f"モジュールインポートエラー: {e}")
            self._log_status(f"❌ モジュールインポートエラー: {e}", error=True)
            self._show_error(f"機能の実行に必要なモジュールが見つかりません\n{e}")
        except Exception as e:
            logger.error(f"画像ファイル一括取得エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_status(f"❌ 画像ファイル一括取得エラー: {e}", error=True)
            self._show_error(f"画像ファイル一括取得エラー\n{e}")
    
    def _update_file_list_display(self, file_list: list):
        """
        ファイルリスト表示を更新
        
        Args:
            file_list: ファイル情報リスト [{'name': ..., 'size': ..., 'path': ..., 'relative_path': ...}, ...]
        """
        try:
            from qt_compat.core import Qt
            from qt_compat.widgets import QTableWidgetItem

            self._clear_file_list_table()

            if not file_list:
                self.file_list_group.setVisible(False)
                return

            self.file_list_group.setVisible(True)

            status_available, existing_images = self._get_existing_image_names()

            self.file_list_widget.blockSignals(True)
            self.file_list_widget.setSortingEnabled(False)
            self.file_list_widget.setRowCount(len(file_list))

            for row, file_info in enumerate(file_list):
                # 0: チェック
                check_item = QTableWidgetItem("")
                check_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
                check_item.setCheckState(Qt.Unchecked)
                self.file_list_widget.setItem(row, 0, check_item)

                # 1: ファイル名
                name_item = QTableWidgetItem(str(file_info.get('name', '')))
                name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                name_item.setData(Qt.UserRole, file_info)
                name_item.setToolTip(
                    f"相対パス: {file_info.get('relative_path', '')}\n"
                    f"フルパス: {file_info.get('path', '')}\n"
                    f"サイズ: {file_info.get('size', 0):,} bytes"
                )
                self.file_list_widget.setItem(row, 1, name_item)

                # 2: キャプション（編集可）
                cached_caption = self._image_caption_cache.get(str(file_info.get('path', '')), "")
                caption_item = QTableWidgetItem(cached_caption)
                caption_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                self.file_list_widget.setItem(row, 2, caption_item)

                # 3: アップロード表示（Up済のみ）
                caption_to_check = self._decide_image_caption(name_item.text(), caption_item.text())
                upload_text = "Up済" if (status_available and caption_to_check in existing_images) else ""
                upload_item = QTableWidgetItem(upload_text)
                upload_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.file_list_widget.setItem(row, 3, upload_item)

            self.file_list_widget.setSortingEnabled(True)
            self.file_list_widget.blockSignals(False)

            self._log_status(f"ファイルリスト表示: {len(file_list)}件")
            self._update_image_upload_button_state()

        except Exception as e:
            logger.error(f"ファイルリスト表示エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            try:
                self.file_list_widget.blockSignals(False)
            except Exception:
                pass

    def _clear_file_list_table(self):
        """取得済みファイル一覧テーブルをクリア（ヘッダは保持）"""
        try:
            self.file_list_widget.setSortingEnabled(False)
            self.file_list_widget.clearContents()
            self.file_list_widget.setRowCount(0)
        finally:
            self.file_list_widget.setSortingEnabled(True)

    def _on_file_table_item_changed(self, item):
        """キャプション編集をキャッシュし、アップロード表示も更新"""
        try:
            from qt_compat.core import Qt

            if item is None:
                return
            if item.column() != 2:
                return

            row = item.row()
            name_item = self.file_list_widget.item(row, 1)
            if name_item is None:
                return
            file_info = name_item.data(Qt.UserRole)
            if not file_info:
                return

            file_path = str(file_info.get('path', ''))
            self._image_caption_cache[file_path] = item.text()

            # キャプション変更により既存画像判定が変わるのでアップロード表示を更新
            self._refresh_upload_status_for_row(row)

        except Exception as e:
            logger.debug(f"file table itemChanged handling failed: {e}")

    def _refresh_upload_status_for_row(self, row: int):
        try:
            from qt_compat.core import Qt

            name_item = self.file_list_widget.item(row, 1)
            caption_item = self.file_list_widget.item(row, 2)
            status_item = self.file_list_widget.item(row, 3)
            if name_item is None or caption_item is None or status_item is None:
                return

            status_available, existing_images = self._get_existing_image_names()
            caption_to_check = self._decide_image_caption(name_item.text(), caption_item.text())
            status_item.setText("Up済" if (status_available and caption_to_check in existing_images) else "")

        except Exception as e:
            logger.debug(f"refresh upload status failed: {e}")

    @staticmethod
    def _decide_image_caption(filename: str, caption_text: Optional[str]) -> str:
        caption = (caption_text or "").strip()
        return caption if caption else filename
    
    def _get_existing_image_names(self, force_refresh: bool = False) -> Tuple[bool, Set[str]]:
        """データポータル上の既存画像名を取得しキャッシュする"""
        dataset_id = self.current_dataset_id
        if not dataset_id:
            return False, set()
        if not force_refresh and dataset_id in self._existing_images_cache:
            return True, self._existing_images_cache[dataset_id]
        if not self.portal_client:
            logger.debug("portal_clientが未初期化のため既存画像を確認できません")
            return False, set()
        t_code = self._get_t_code_for_dataset(dataset_id)
        if not t_code:
            logger.warning(f"t_code未取得のため既存画像を確認できません: {dataset_id}")
            return False, set()
        existing_images = self._get_existing_images(t_code)
        self._existing_images_cache[dataset_id] = existing_images
        return True, existing_images
    
    def _update_image_upload_button_state(self):
        """
        画像アップロードボタンの有効/無効を更新
        
        条件:
        - JSONアップロード完了済み OR データポータル修正ボタンが有効（エントリ登録済み）
        - ファイルリストに1件以上のファイルがある
        """
        has_files = self.file_list_widget.rowCount() > 0
        # JSONアップロード済み、またはデータポータル修正ボタンが有効（既存エントリ）
        entry_exists = self.json_uploaded or self.edit_portal_btn.isEnabled()
        can_upload = entry_exists and has_files
        
        self.upload_images_btn.setEnabled(can_upload)
        
        if not entry_exists and has_files:
            self.upload_images_btn.setToolTip("先に書誌情報JSONをアップロードしてください")
        elif can_upload:
            self.upload_images_btn.setToolTip("チェックした画像をデータポータルにアップロードします")
        else:
            self.upload_images_btn.setToolTip("画像ファイルを取得してください")

    def _update_zip_upload_button_state(self) -> None:
        """コンテンツZIPアップロードボタンの有効/無効を更新。

        要件:
        - データカタログ修正ボタンが有効な場合のみZIPアップロードを有効
        - 環境別の認証情報（ログイン設定）が必須
        """

        try:
            if not hasattr(self, "upload_zip_btn") or self.upload_zip_btn is None:
                return

            environment = self.current_environment or self.env_combo.currentData()
            has_creds = bool(environment and self.auth_manager.has_credentials(environment))
            can_upload = bool(self.current_dataset_id) and bool(self.edit_portal_btn.isEnabled()) and has_creds

            worker = getattr(self, "contents_zip_upload_worker", None)
            if worker is not None and hasattr(worker, "isRunning") and worker.isRunning():
                can_upload = False

            self.upload_zip_btn.setEnabled(can_upload)

            if not self.current_dataset_id:
                self.upload_zip_btn.setToolTip("データセットを選択してください")
            elif not self.edit_portal_btn.isEnabled():
                self.upload_zip_btn.setToolTip("データカタログ修正が有効なデータセットのみZIPアップロードできます")
            elif not has_creds:
                self.upload_zip_btn.setToolTip("認証情報が未設定です。『ログイン設定』タブで保存してください")
            else:
                self.upload_zip_btn.setToolTip("ローカルZIPアップロード、またはRDEから自動取得してZIP化→アップロードを選択できます")
        except Exception as e:
            logger.debug(f"ZIPアップロードボタン状態更新エラー: {e}")
    
    def eventFilter(self, obj, event):
        """
        イベントフィルタ: スペースキーでチェックボックスのオン/オフ
        
        Args:
            obj: イベントを受け取るオブジェクト
            event: イベント
        
        Returns:
            bool: イベントを処理した場合True
        """
        try:
            from qt_compat.core import QEvent
            from qt_compat.gui import QKeyEvent
            from qt_compat.core import Qt
            
            if obj == self.file_list_widget and event.type() == QEvent.KeyPress:
                key_event = event
                if key_event.key() == Qt.Key_Space:
                    row = self.file_list_widget.currentRow()
                    if row >= 0:
                        check_item = self.file_list_widget.item(row, 0)
                        if check_item is not None:
                            new_state = Qt.Unchecked if check_item.checkState() == Qt.Checked else Qt.Checked
                            check_item.setCheckState(new_state)
                            logger.debug(f"スペースキーでチェックをトグル: row={row}, checked={new_state == Qt.Checked}")
                        return True
            
        except Exception as e:
            logger.error(f"イベントフィルタエラー: {e}")
        
        return super().eventFilter(obj, event)
    
    def _on_file_table_current_cell_changed(self, current_row: int, current_col: int, previous_row: int, previous_col: int):
        """ファイル一覧の選択変更時にプレビューを更新"""
        if current_row >= 0:
            self._show_file_preview_for_row(current_row)

    def _show_file_preview_for_row(self, row: int):
        """テーブル行からファイル情報を取得してプレビュー表示"""
        try:
            from qt_compat.gui import QPixmap
            from qt_compat.core import Qt

            name_item = self.file_list_widget.item(row, 1)
            if name_item is None:
                self.thumbnail_label.setText("ファイル情報が見つかりません")
                return

            file_info = name_item.data(Qt.UserRole)
            if not file_info:
                self.thumbnail_label.setText("ファイル情報が見つかりません")
                return
            
            file_path = file_info['path']
            
            # 画像ファイルかチェック
            if not file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp')):
                self.thumbnail_label.setText("画像ファイルではありません")
                return
            
            # サムネイル画像をロード
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                self.thumbnail_label.setText("画像を読み込めません")
                return
            
            # サムネイルサイズにスケール
            scaled_pixmap = pixmap.scaled(
                200, 200,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            
            self.thumbnail_label.setPixmap(scaled_pixmap)
            
        except Exception as e:
            logger.error(f"サムネイル表示エラー: {e}")
            self.thumbnail_label.setText("エラーが発生しました")
    
    def _on_select_all_files(self):
        """全選択ボタンの処理"""
        try:
            from qt_compat.core import Qt

            for row in range(self.file_list_widget.rowCount()):
                check_item = self.file_list_widget.item(row, 0)
                if check_item is not None:
                    check_item.setCheckState(Qt.Checked)
            
            self._log_status("全ファイルを選択しました")
            
        except Exception as e:
            logger.error(f"全選択エラー: {e}")
    
    def _on_deselect_all_files(self):
        """全解除ボタンの処理"""
        try:
            from qt_compat.core import Qt

            for row in range(self.file_list_widget.rowCount()):
                check_item = self.file_list_widget.item(row, 0)
                if check_item is not None:
                    check_item.setCheckState(Qt.Unchecked)
            
            self._log_status("全ファイルの選択を解除しました")
            
        except Exception as e:
            logger.error(f"全解除エラー: {e}")
    
    def _on_open_files_folder(self):
        """ファイルフォルダを開く（データ取得2と同じ構造）"""
        if not self.current_dataset_id:
            self._show_warning("データセットが選択されていません")
            return
        
        try:
            from qt_compat.core import QUrl
            from qt_compat.gui import QDesktopServices
            
            dataset_id = self.current_dataset_id
            
            # データセット情報を取得
            dataset_info = self._get_dataset_info_from_json(dataset_id)
            if not dataset_info:
                self._show_warning("データセット情報が取得できません")
                return
            
            grant_number = dataset_info.get('grantNumber', '不明')
            
            # パス無効文字の置換
            def replace_invalid_path_chars(s):
                if not s:
                    return ""
                table = str.maketrans({
                    '\\': '￥', '/': '／', ':': '：', '*': '＊',
                    '?': '？', '"': '"', '<': '＜', '>': '＞', '|': '｜',
                })
                return s.translate(table)
            
            safe_grant_number = replace_invalid_path_chars(grant_number)
            
            # grantNumberフォルダを開く（データ取得2と同じ階層）
            files_dir = get_dynamic_file_path(f"output/rde/data/dataFiles/{safe_grant_number}")
            
            if not os.path.exists(files_dir):
                self._show_warning(f"フォルダが存在しません: {files_dir}")
                return
            
            # エクスプローラーでフォルダを開く
            QDesktopServices.openUrl(QUrl.fromLocalFile(files_dir))
            self._log_status(f"フォルダを開きました: {files_dir}")
            
        except Exception as e:
            logger.error(f"フォルダを開くエラー: {e}")
    
    def _on_upload_images(self):
        """
        チェックした画像をData Serviceにアップロード
        
        フロー:
        1. JSONアップロード後の書誌情報一覧ページに遷移
        2. 画像管理画面に移動
        3. 新規登録画面を開く
        4. チェックした各ファイルをアップロード
        5. 完了後、画像一覧に戻る
        """
        if not self.current_dataset_id:
            self._show_warning("データセットが選択されていません")
            return
        
        try:
            # チェックされたファイルを取得
            checked_files = []
            for row in range(self.file_list_widget.rowCount()):
                check_item = self.file_list_widget.item(row, 0)
                name_item = self.file_list_widget.item(row, 1)
                caption_item = self.file_list_widget.item(row, 2)
                if check_item is None or name_item is None:
                    continue
                if check_item.checkState() != Qt.Checked:
                    continue

                file_info = name_item.data(Qt.UserRole)
                if not file_info:
                    continue
                caption_text = caption_item.text() if caption_item is not None else ""
                upload_caption = self._decide_image_caption(str(file_info.get('name', '')), caption_text)

                merged = dict(file_info)
                merged['caption'] = upload_caption
                checked_files.append(merged)
            
            if not checked_files:
                self._show_warning("アップロードするファイルが選択されていません。\nチェックボックスでファイルを選択してください。")
                return
            
            # 確認ダイアログ
            reply = QMessageBox.question(
                self,
                "画像アップロード確認",
                f"選択された {len(checked_files)} 件のファイルをData Serviceにアップロードしますか?\n\n"
                "この操作には時間がかかる場合があります。",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # データセット情報を取得（t_code用）
            dataset_info = self._get_dataset_info_from_json(self.current_dataset_id)
            if not dataset_info:
                self._show_error("データセット情報が取得できません")
                return
            
            # t_codeを取得（書誌情報一覧ページから抽出）
            self._log_status("t_codeを取得中...")
            t_code = self._get_t_code_for_dataset(self.current_dataset_id)
            
            if not t_code:
                self._show_error(f"データセットID {self.current_dataset_id} に対応するt_codeが見つかりません")
                return
            
            self._log_status(f"t_code取得成功: {t_code}")
            
            self._log_status(f"画像アップロード開始: {len(checked_files)}件")
            
            # プログレスダイアログ
            from qt_compat.widgets import QProgressDialog, QApplication
            progress = QProgressDialog("画像をアップロード中...", "キャンセル", 0, len(checked_files), self)
            progress.setWindowTitle("画像アップロード")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            QApplication.processEvents()
            
            # Step 1: 書誌情報一覧ページに遷移
            self._log_status("書誌情報一覧ページに遷移中...")
            success, response = self._navigate_to_bibliography_list(t_code)
            if not success:
                self._show_error(f"書誌情報一覧ページへの遷移に失敗しました: {response}")
                progress.close()
                return
            
            # Step 2: 画像管理画面に移動
            self._log_status("画像管理画面に移動中...")
            success, response = self._navigate_to_image_management(t_code)
            if not success:
                self._show_error(f"画像管理画面への移動に失敗しました: {response}")
                progress.close()
                return
            
            # Step 3: 既存画像一覧を取得
            self._log_status("既存画像をチェック中...")
            existing_images = self._get_existing_images(t_code)
            
            # 既存画像との重複チェック
            duplicate_files = []
            new_files = []
            
            for file_info in checked_files:
                caption = file_info.get('caption')
                if caption and caption in existing_images:
                    duplicate_files.append(file_info)
                else:
                    new_files.append(file_info)
            
            # 重複がある場合は確認ダイアログ
            files_to_upload = []
            if duplicate_files:
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("既存画像の確認")
                msg_box.setText(
                    f"{len(duplicate_files)} 件の画像は既にアップロード済みです:\n\n" +
                    "\n".join([f"• {f['name']}" for f in duplicate_files[:5]]) +
                    (f"\n... 他 {len(duplicate_files) - 5} 件" if len(duplicate_files) > 5 else "") +
                    f"\n\n新規: {len(new_files)} 件\n重複: {len(duplicate_files)} 件\n\n"
                    "重複ファイルの扱いを選択してください:"
                )
                msg_box.setIcon(QMessageBox.Question)
                
                # カスタムボタン
                skip_btn = msg_box.addButton("重複をスキップ", QMessageBox.YesRole)
                force_btn = msg_box.addButton("強制アップロード（追加）", QMessageBox.NoRole)
                cancel_btn = msg_box.addButton("キャンセル", QMessageBox.RejectRole)
                
                msg_box.setDefaultButton(skip_btn)
                msg_box.exec()
                
                clicked_button = msg_box.clickedButton()
                
                if clicked_button == skip_btn:
                    # 重複をスキップ
                    files_to_upload = new_files
                    self._log_status(f"重複をスキップ: {len(new_files)}件をアップロード")
                elif clicked_button == force_btn:
                    # 強制アップロード（上書きではなく追加）
                    files_to_upload = checked_files
                    self._log_status(f"強制アップロード: {len(checked_files)}件をアップロード（追加）")
                    QMessageBox.information(
                        self,
                        "注意",
                        "強制アップロードは上書きではなく、追加アップロードとなります。\n\n"
                        "既存の画像を削除したい場合は、管理者にご連絡ください。"
                    )
                else:
                    # キャンセル
                    progress.close()
                    self._log_status("画像アップロードをキャンセルしました")
                    return
            else:
                # 重複なし
                files_to_upload = new_files
                self._log_status(f"新規画像のみ: {len(new_files)}件")
            
            if not files_to_upload:
                progress.close()
                self._show_info("アップロードする画像がありません")
                return
            
            # Step 4: 新規登録画面を開く
            self._log_status("新規登録画面を開いています...")
            success, response = self._navigate_to_image_register(t_code)
            if not success:
                self._show_error(f"新規登録画面を開くのに失敗しました: {response}")
                progress.close()
                return
            
            # Step 5: 各ファイルをアップロード
            progress.setMaximum(len(files_to_upload))
            upload_count = 0
            for idx, file_info in enumerate(files_to_upload):
                if progress.wasCanceled():
                    break
                
                progress.setValue(idx)
                progress.setLabelText(f"アップロード中: {file_info['name']}\n({idx+1}/{len(files_to_upload)})")
                QApplication.processEvents()
                
                # ファイルをアップロード
                success, message = self._upload_single_image(
                    t_code=t_code,
                    file_path=file_info['path'],
                    original_filename=file_info['name'],
                    caption=file_info.get('caption') or file_info['name']
                )
                
                if success:
                    upload_count += 1
                    self._log_status(f"✅ [{idx+1}/{len(files_to_upload)}] {file_info['name']} - アップロード成功")
                else:
                    self._log_status(f"❌ [{idx+1}/{len(files_to_upload)}] {file_info['name']} - 失敗: {message}", error=True)
            
            progress.setValue(len(files_to_upload))
            progress.close()
            
            # Step 6: 完了メッセージ
            if upload_count > 0:
                result_msg = f"画像アップロードが完了しました\n\n"
                result_msg += f"成功: {upload_count}件\n"
                result_msg += f"失敗: {len(files_to_upload) - upload_count}件"
                if duplicate_files and files_to_upload == new_files:
                    result_msg += f"\nスキップ: {len(duplicate_files)}件"
                
                self._log_status(f"✅ 画像アップロード完了: {upload_count}/{len(files_to_upload)}件")
                self._show_info(result_msg)
                if self.current_dataset_id:
                    self._existing_images_cache.pop(self.current_dataset_id, None)
                    _, _, refreshed_files = self._check_files_exist(self.current_dataset_id)
                    self._update_file_list_display(refreshed_files)
            else:
                self._log_status("⚠️ 画像アップロードに失敗しました", error=True)
                self._show_warning("画像をアップロードできませんでした")
                
        except Exception as e:
            logger.error(f"画像アップロードエラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_status(f"❌ 画像アップロードエラー: {e}", error=True)
            self._show_error(f"画像アップロードエラー\n{e}")
    
    def _save_debug_response(self, step_name: str, response_text: str):
        """
        デバッグ用レスポンス保存
        
        Args:
            step_name: ステップ名
            response_text: レスポンステキスト
        """
        try:
            from datetime import datetime
            
            debug_dir = get_dynamic_file_path("output/data_portal_debug/image_upload")
            os.makedirs(debug_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(debug_dir, f"{step_name}_{timestamp}.html")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(response_text)
            
            logger.info(f"[DEBUG] レスポンス保存: {filepath}")
            self._log_status(f"🔍 デバッグ保存: {step_name}")
            
        except Exception as e:
            logger.error(f"デバッグレスポンス保存エラー: {e}")
    
    def _get_existing_images(self, t_code: str) -> set:
        """
        既存の画像一覧（キャプション）を取得
        
        Args:
            t_code: テーマコード
        
        Returns:
            set: 既存画像のキャプション名のセット
        """
        try:
            import re
            
            logger.info(f"[GET_IMAGES] t_code={t_code} の既存画像を取得中...")
            
            # 画像一覧ページを取得
            data = {
                'mode': 'theme',
                'mode2': 'image',
                't_code': t_code,
                'keyword': '',
                'search_inst': '',
                'search_license_level': '',
                'search_status': '',
                'page': '1'
            }
            
            success, response = self.portal_client.post("main.php", data=data)
            
            if not success or not hasattr(response, 'text'):
                logger.error("[GET_IMAGES] 画像一覧ページの取得に失敗")
                return set()
            
            # デバッグ保存
            self._save_debug_response("get_existing_images", response.text)
            
            # キャプション（ti_title）を抽出
            # パターン: <td class="l">キャプション名</td>
            # 画像テーブルの構造に合わせて調整が必要
            pattern = r'<td class="l">([^<]+)</td>'
            matches = re.findall(pattern, response.text)
            
            # 重複を除去してセットに変換
            existing_captions = set(matches)
            
            logger.info(f"[GET_IMAGES] 既存画像: {len(existing_captions)}件")
            
            return existing_captions
            
        except Exception as e:
            logger.error(f"既存画像取得エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return set()
    
    def _get_t_code_for_dataset(self, dataset_id: str) -> str:
        """
        データセットIDに対応するt_codeを取得
        
        Args:
            dataset_id: データセットID
        
        Returns:
            str: t_code（見つからない場合は空文字列）
        """
        try:
            import re

            dsid = str(dataset_id or "").strip()
            if not dsid:
                return ""

            current_id = str(self.current_dataset_id or "").strip()
            cached_t_code = str(self.current_t_code or "").strip()
            if cached_t_code and current_id and current_id == dsid:
                logger.info(f"[GET_T_CODE] キャッシュ済みt_codeを使用: {cached_t_code} (データセットID: {dsid})")
                return cached_t_code

            if not self.portal_client:
                logger.error("[GET_T_CODE] portal_client が未初期化です")
                return ""
            
            # 書誌情報一覧ページを取得
            logger.info(f"[GET_T_CODE] データセットID {dsid} のt_codeを検索中...")
            data = {
                'mode': 'theme',
                'keyword': dsid,
                'search_inst': '',
                'search_license_level': '',
                'search_status': '',
                'page': '1',
            }
            success, response = self.portal_client.post("main.php", data=data)
            
            if not success or not hasattr(response, 'text'):
                logger.error("[GET_T_CODE] 書誌情報一覧ページの取得に失敗")
                return ""
            
            # デバッグ保存
            self._save_debug_response("get_t_code_bibliography_search", response.text)

            try:
                from classes.data_portal.core.portal_entry_status import parse_portal_entry_search_html

                env = self.current_environment or self.env_combo.currentData() or 'production'
                parsed = parse_portal_entry_search_html(response.text, dsid, environment=str(env))
                parsed_t_code = str(parsed.t_code or '').strip()
                if parsed_t_code:
                    if current_id and current_id == dsid:
                        self.current_t_code = parsed_t_code
                    logger.info(f"[GET_T_CODE] パーサーでt_code取得成功: {parsed_t_code} (データセットID: {dsid})")
                    return parsed_t_code
            except Exception:
                pass
            
            # データセットIDとt_codeの対応を抽出
            # パターン: <td class="l">データセットID</td> の後に <input type="hidden" name="t_code" value="272">
            pattern = rf'<td class="l">{re.escape(dsid)}</td>.*?name="t_code" value="([^"\']+)"'
            match = re.search(pattern, response.text, re.DOTALL)
            
            if match:
                t_code = str(match.group(1) or "").strip()
                if current_id and current_id == dsid and t_code:
                    self.current_t_code = t_code
                logger.info(f"[GET_T_CODE] t_code取得成功: {t_code} (データセットID: {dsid})")
                return t_code
            
            logger.warning(f"[GET_T_CODE] データセットID {dsid} に対応するt_codeが見つかりません")
            return ""
            
        except Exception as e:
            logger.error(f"t_code取得エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ""
    
    def _navigate_to_bibliography_list(self, t_code: str) -> Tuple[bool, Any]:
        """
        書誌情報一覧ページに遷移
        
        Args:
            t_code: テーマコード
        
        Returns:
            Tuple[bool, Any]: (成功フラグ, レスポンスまたはエラーメッセージ)
        """
        try:
            data = {
                'mode': 'theme',
                't_code': t_code,
                'keyword': '',
                'page': '1'
            }
            
            logger.info(f"[STEP1] 書誌情報一覧ページに遷移: t_code={t_code}")
            success, response = self.portal_client.post("main.php", data=data)
            
            if success and hasattr(response, 'text'):
                self._save_debug_response("step1_bibliography_list", response.text)
                logger.info(f"[STEP1] レスポンスサイズ: {len(response.text)} bytes")
            
            return success, response
            
        except Exception as e:
            logger.error(f"書誌情報一覧ページ遷移エラー: {e}")
            return False, str(e)
    
    def _navigate_to_image_management(self, t_code: str) -> Tuple[bool, Any]:
        """
        画像管理画面に移動
        
        Args:
            t_code: テーマコード
        
        Returns:
            Tuple[bool, Any]: (成功フラグ, レスポンスまたはエラーメッセージ)
        """
        try:
            data = {
                'mode': 'theme',
                'mode2': 'image',
                't_code': t_code,
                'keyword': '',
                'search_inst': '',
                'search_license_level': '',
                'search_status': '',
                'page': '1'
            }
            
            logger.info(f"[STEP2] 画像管理画面に移動: t_code={t_code}")
            success, response = self.portal_client.post("main.php", data=data)
            
            if success and hasattr(response, 'text'):
                self._save_debug_response("step2_image_management", response.text)
                logger.info(f"[STEP2] レスポンスサイズ: {len(response.text)} bytes")
            
            return success, response
            
        except Exception as e:
            logger.error(f"画像管理画面遷移エラー: {e}")
            return False, str(e)
    
    def _navigate_to_image_register(self, t_code: str) -> Tuple[bool, Any]:
        """
        画像新規登録画面を開く
        
        Args:
            t_code: テーマコード
        
        Returns:
            Tuple[bool, Any]: (成功フラグ, レスポンスまたはエラーメッセージ)
        """
        try:
            data = {
                'mode': 'theme',
                'mode2': 'image',
                'mode3': 'regist',
                'ti_code': '0',
                't_code': t_code,
                'keyword': '',
                'page': '1'
            }
            
            logger.info(f"[STEP3] 画像新規登録画面を開く: t_code={t_code}")
            success, response = self.portal_client.post("main.php", data=data)
            
            if success and hasattr(response, 'text'):
                self._save_debug_response("step3_image_register", response.text)
                logger.info(f"[STEP3] レスポンスサイズ: {len(response.text)} bytes")
            
            return success, response
            
        except Exception as e:
            logger.error(f"画像新規登録画面遷移エラー: {e}")
            return False, str(e)
    
    def _upload_single_image(self, t_code: str, file_path: str, original_filename: str, caption: str) -> Tuple[bool, str]:
        """
        単一の画像ファイルをアップロード
        
        正しいフロー:
        1. 新規登録画面でファイルをアップロード (mode4=conf で確認画面へ)
        2. 確認画面から登録確定 (mode4=rec で登録)
        
        Args:
            t_code: テーマコード（数値）
            file_path: アップロードするファイルのパス
            original_filename: オリジナルのファイル名
            caption: データポータルに登録するキャプション
        
        Returns:
            Tuple[bool, str]: (成功フラグ, メッセージ)
        """
        try:
            logger.info(f"[STEP4] 画像アップロード開始: {original_filename}, t_code={t_code}, caption={caption}")
            
            # Step 1: ファイルをアップロードして確認画面へ (mode4=conf)
            with open(file_path, 'rb') as f:
                files = {
                    'upload_file': (original_filename, f, 'image/jpeg')
                }
                
                data = {
                    'mode': 'theme',
                    'mode2': 'image',
                    'mode3': 'regist',
                    'mode4': 'conf',  # 確認画面へ
                    'ti_code': '0',
                    'ti_title': caption,  # キャプション
                    't_code': t_code,  # 数値のt_code
                    'keyword': '',
                    'page': '1'
                }
                
                logger.info(f"[STEP4-1] ファイルアップロード(確認画面へ): {original_filename} ({os.path.getsize(file_path)} bytes), t_code={t_code}")
                success, response = self.portal_client.post("main.php", data=data, files=files)
                
                if not success:
                    logger.error(f"[STEP4-1] ファイルアップロード失敗: {response}")
                    return False, f"ファイルアップロード失敗: {response}"
                
                # デバッグ: レスポンスを保存
                if hasattr(response, 'text'):
                    self._save_debug_response(f"step4_1_confirm_{original_filename.replace(' ', '_')}", response.text)
                    logger.info(f"[STEP4-1] レスポンスサイズ: {len(response.text)} bytes")
                    
                    # エラーチェック
                    if 'Warning' in response.text or 'ERROR' in response.text:
                        logger.error("[STEP4-1] レスポンスにエラーが含まれています")
                        # エラーメッセージを抽出
                        import re
                        error_match = re.search(r'<b>(Warning|ERROR)[^<]*</b>:([^<]+)', response.text)
                        if error_match:
                            error_msg = error_match.group(0)
                            logger.error(f"[STEP4-1] エラー内容: {error_msg}")
                            return False, f"サーバーエラー: {error_msg}"
                
                # レスポンスから temp_filename を抽出
                temp_filename = self._extract_temp_filename(response.text)
                
                if not temp_filename:
                    logger.error("[STEP4-1] temp_filename が抽出できませんでした")
                    return False, "一時ファイル名の取得に失敗しました"
                else:
                    logger.info(f"[STEP4-1] temp_filename 抽出成功: {temp_filename}")
            
            # Step 2: 確認画面から登録確定 (mode4=rec)
            data = {
                'mode': 'theme',
                'mode2': 'image',
                'mode3': 'regist',
                'mode4': 'rec',  # 登録確定
                'ti_code': '0',
                'ti_title': caption,  # キャプション
                'ti_file': temp_filename,  # 一時ファイル名
                'original_filename': original_filename,
                'old_filename': '',
                'file_delete_flag': '',
                'file_change_flag': '1',
                't_code': t_code,  # 数値のt_code
                'keyword': '',
                'page': '1'
            }
            
            logger.info(f"[STEP4-2] 画像登録確定: ti_title={caption}, ti_file={temp_filename}, t_code={t_code}")
            success, response = self.portal_client.post("main.php", data=data)
            
            # デバッグ: レスポンスを保存
            if hasattr(response, 'text'):
                self._save_debug_response(f"step4_2_complete_{original_filename.replace(' ', '_')}", response.text)
                logger.info(f"[STEP4-2] レスポンスサイズ: {len(response.text)} bytes")
                
                # エラーチェック
                if 'Warning' in response.text or 'ERROR' in response.text:
                    logger.error("[STEP4-2] レスポンスにエラーが含まれています")
                    import re
                    error_match = re.search(r'<b>(Warning|ERROR)[^<]*</b>:([^<]+)', response.text)
                    if error_match:
                        error_msg = error_match.group(0)
                        logger.error(f"[STEP4-2] エラー内容: {error_msg}")
                        return False, f"登録エラー: {error_msg}"
            
            if success:
                logger.info(f"[STEP4] アップロード成功: {original_filename}")
                return True, "アップロード成功"
            else:
                logger.error(f"[STEP4-2] 登録失敗: {response}")
                return False, f"登録失敗: {response}"
                
        except Exception as e:
            logger.error(f"画像アップロードエラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, str(e)
    
    def _extract_temp_filename(self, response_text: str) -> str:
        """
        レスポンスHTMLから temp_filename を抽出
        
        Args:
            response_text: レスポンスHTML
        
        Returns:
            str: 一時ファイル名（抽出できない場合は空文字列）
        """
        try:
            import re
            
            # パターン1: input要素のvalue属性から抽出
            # <input type="hidden" name="ti_file" value="temp_0000000155.jpeg">
            pattern1 = r'<input[^>]*name=["\']ti_file["\'][^>]*value=["\']([^"\']+)["\']'
            match = re.search(pattern1, response_text, re.IGNORECASE)
            if match:
                temp_filename = match.group(1)
                logger.info(f"[EXTRACT] パターン1でtemp_filename抽出成功: {temp_filename}")
                return temp_filename
            
            # パターン2: JavaScriptの変数から抽出
            # var temp_file = "temp_0000000155.jpeg";
            pattern2 = r'temp_file\s*=\s*["\']([^"\']+)["\']'
            match = re.search(pattern2, response_text, re.IGNORECASE)
            if match:
                temp_filename = match.group(1)
                logger.info(f"[EXTRACT] パターン2でtemp_filename抽出成功: {temp_filename}")
                return temp_filename
            
            # パターン3: temp_で始まるファイル名を探す
            pattern3 = r'(temp_\d+\.(jpeg|jpg|png))'
            match = re.search(pattern3, response_text, re.IGNORECASE)
            if match:
                temp_filename = match.group(1)
                logger.info(f"[EXTRACT] パターン3でtemp_filename抽出成功: {temp_filename}")
                return temp_filename
            
            logger.warning("[EXTRACT] temp_filename が見つかりませんでした")
            return ""
            
        except Exception as e:
            logger.error(f"temp_filename抽出エラー: {e}")
            return ""
    
    def _check_rde_dataset_exists(self, dataset_id: str) -> bool:
        """
        RDEサイト上にデータセットが存在するか確認
        
        Args:
            dataset_id: データセットID
            
        Returns:
            bool: 存在する場合True
        """
        try:
            from net.http_helpers import proxy_get
            
            # RDEサイトのデータセットページにアクセス
            dataset_url = f"https://rde.nims.go.jp/rde/datasets/{dataset_id}"
            logger.info(f"[RDE_CHECK] データセット存在確認: {dataset_url}")
            
            response = proxy_get(dataset_url, allow_redirects=False)
            
            # 200 OKならデータセットが存在
            exists = response.status_code == 200
            logger.info(f"[RDE_CHECK] ステータスコード: {response.status_code}, 存在: {exists}")
            
            return exists
            
        except Exception as e:
            logger.error(f"[RDE_CHECK] データセット存在確認エラー: {e}")
            return False
    
    def _check_portal_entry_exists(self, dataset_id: str):
        """
        データポータルにエントリが存在するか確認
        
        Args:
            dataset_id: データセットID
        """
        try:
            if not self.portal_client:
                self.edit_portal_btn.setEnabled(False)
                self._update_zip_upload_button_state()
                return
            
            logger.info(f"[CHECK_ENTRY] ===== エントリ確認開始 =====")
            logger.info(f"[CHECK_ENTRY] データセットID: {dataset_id}")
            logger.info(f"[CHECK_ENTRY] portal_client: {self.portal_client}")
            logger.info(f"[CHECK_ENTRY] 認証情報設定済み: {self.portal_client.credentials is not None}")
            
            # データセットIDで検索（認証情報は既に設定済みと仮定）
            data = {
                'mode': 'theme',
                'keyword': dataset_id,
                'search_inst': '',
                'search_license_level': '',
                'search_status': '',
                'page': '1'
            }
            
            logger.info(f"[CHECK_ENTRY] POST data: {data}")
            success, response = self.portal_client.post("main.php", data=data)
            
            logger.info(f"[CHECK_ENTRY] リクエスト完了 - success={success}, response type={type(response)}")
            
            if not success or not hasattr(response, 'text'):
                logger.warning(f"[CHECK_ENTRY] 検索失敗 - success={success}, has_text={hasattr(response, 'text') if response else False}")
                self.edit_portal_btn.setEnabled(False)
                self._update_zip_upload_button_state()
                return
            
            # デバッグ保存
            self._save_debug_response(f"check_entry_{dataset_id}", response.text)
            logger.info(f"[CHECK_ENTRY] レスポンスサイズ: {len(response.text)} bytes")
            
            # ログインページが返された場合は再ログイン
            if 'ログイン' in response.text or 'Login' in response.text or 'loginArea' in response.text:
                logger.warning("[CHECK_ENTRY] ログインページが返されました - 再ログイン実行")
                login_success, login_message = self.portal_client.login()
                
                if not login_success:
                    logger.error(f"[CHECK_ENTRY] 再ログイン失敗: {login_message}")
                    self.edit_portal_btn.setEnabled(False)
                    self._update_zip_upload_button_state()
                    return
                
                logger.info(f"[CHECK_ENTRY] 再ログイン成功 - 検索を再試行")
                
                # 再度検索実行
                success, response = self.portal_client.post("main.php", data=data)
                
                if not success or not hasattr(response, 'text'):
                    logger.error("[CHECK_ENTRY] 再検索失敗")
                    self.edit_portal_btn.setEnabled(False)
                    self._update_zip_upload_button_state()
                    return
                
                self._save_debug_response(f"check_entry_{dataset_id}_retry", response.text)
                logger.info(f"[CHECK_ENTRY] 再検索成功 - レスポンスサイズ: {len(response.text)} bytes")
            
            # データセットIDがレスポンスに含まれるかチェック
            dataset_id_found = dataset_id in response.text
            logger.info(f"[CHECK_ENTRY] データセットID存在チェック: {dataset_id_found}")

            from classes.data_portal.core.portal_entry_status import parse_portal_entry_search_html
            from classes.data_portal.core.portal_entry_status import parse_portal_contents_link_search_html

            env = self.current_environment or self.env_combo.currentData() or 'production'
            parsed = parse_portal_entry_search_html(response.text, dataset_id, environment=str(env))

            # コンテンツリンク有無（コンテンツZIPアップ済み判定）
            try:
                has_contents = parse_portal_contents_link_search_html(response.text, dataset_id)
            except Exception:
                has_contents = None

            # ラベル更新（エントリ未登録や未ログイン時は未確認に寄せる）
            if not parsed.dataset_id_found:
                self._update_contents_zip_status_label(None)
            else:
                self._update_contents_zip_status_label(has_contents)

            # Persist best-effort portal label for dataset listing.
            # "公開（管理）" is determined by the same condition as enabling "非公開にする".
            try:
                if parsed.can_edit:
                    from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache
                    from classes.dataset.util.portal_status_resolver import normalize_logged_in_portal_label

                    label = normalize_logged_in_portal_label(parsed.listing_label())
                    get_portal_entry_status_cache().set_label(str(dataset_id), label, str(env))
            except Exception:
                pass

            # パース結果をウィジェット状態へ反映
            self.current_status = parsed.current_status
            self.current_t_code = parsed.t_code
            self.current_public_code = parsed.public_code
            self.current_public_key = parsed.public_key
            self.current_public_url = parsed.public_url

            if parsed.dataset_id_found and parsed.can_edit:
                logger.info(f"[CHECK_ENTRY] ✅ エントリ存在 - 修正可能")
                self.edit_portal_btn.setEnabled(True)
                self.edit_portal_btn.setToolTip(f"データポータルのエントリを修正します (ID: {dataset_id[:8]}...)")

                # ステータス変更ボタン
                if parsed.can_toggle_status and self.current_status:
                    self.toggle_status_btn.setEnabled(True)
                    if self.current_status == '公開済':
                        self.toggle_status_btn.setText("🔄 非公開にする")
                        self.toggle_status_btn.setToolTip("データポータルのエントリを非公開にします")
                    else:
                        self.toggle_status_btn.setText("🔄 公開する")
                        self.toggle_status_btn.setToolTip("データポータルのエントリを公開します")
                else:
                    self.toggle_status_btn.setEnabled(False)
                    self.toggle_status_btn.setToolTip("ステータス情報が取得できません")

                # 公開ページボタン（code/keyが取れている場合のみ有効化）
                self.public_view_btn.setEnabled(bool(parsed.can_public_view))
            elif parsed.dataset_id_found:
                logger.warning(f"[CHECK_ENTRY] ⚠️ エントリ存在 - 修正リンクが見つかりません")
                self.edit_portal_btn.setEnabled(False)
                self.edit_portal_btn.setToolTip("修正リンクが無効です")
                self.toggle_status_btn.setEnabled(False)
                self.public_view_btn.setEnabled(False)
            else:
                logger.info(f"[CHECK_ENTRY] ⚠️ エントリ未登録")
                self.edit_portal_btn.setEnabled(False)
                self.edit_portal_btn.setToolTip("エントリが登録されていません")
                self.toggle_status_btn.setEnabled(False)
                self.current_t_code = None
                self.current_status = None
                self.public_view_btn.setEnabled(False)
            
            logger.info(f"[CHECK_ENTRY] ===== エントリ確認完了 (ボタン有効: {self.edit_portal_btn.isEnabled()}, ステータス: {self.current_status}) =====")
            
            # 画像アップロードボタンの状態も更新
            self._update_image_upload_button_state()
            self._update_zip_upload_button_state()
                
        except Exception as e:
            logger.error(f"[CHECK_ENTRY] ❌ エラー発生: {e}", exc_info=True)
            self.current_t_code = None
            self.edit_portal_btn.setEnabled(False)
            self.toggle_status_btn.setEnabled(False)
            self._update_image_upload_button_state()
            self._update_zip_upload_button_state()

    def _on_open_public_view(self):
        """公開ページを既定ブラウザで開く"""
        if not (self.current_public_code and self.current_public_key):
            self._show_warning("公開ページのURL情報が取得できていません")
            return
        try:
            # current_public_url が過去の環境（本番）を指している可能性があるため、常に選択環境で組み立て直す
            env = self.current_environment or self.env_combo.currentData() or "production"
            from classes.utils.data_portal_public import build_public_detail_url
            url = build_public_detail_url(env, self.current_public_code, self.current_public_key)
            import webbrowser
            webbrowser.open(url)
            self._log_status(f"🌐 公開ページを開きました: {url}")
        except Exception as e:
            logger.error(f"公開ページ起動エラー: {e}")
            self._show_error(f"公開ページを開く際にエラーが発生しました\n{e}")
    
    def _on_edit_portal(self):
        """データポータル修正処理"""
        if not self.current_dataset_id:
            self._show_warning("データセットが選択されていません")
            return
        
        try:
            # t_codeを取得
            self._log_status("t_codeを取得中...")
            t_code = self._get_t_code_for_dataset(self.current_dataset_id)
            
            if not t_code:
                self._show_error(f"データセットID {self.current_dataset_id} に対応するt_codeが見つかりません")
                return
            
            self._log_status(f"t_code取得成功: {t_code}")
            
            # 修正画面を開く
            self._log_status("修正画面を開いています...")
            success, edit_form_html = self._open_edit_form(t_code, self.current_dataset_id)
            
            if not success:
                self._show_error(f"修正画面を開くのに失敗しました: {edit_form_html}")
                return
            
            # フォームデータを解析
            form_data = self._parse_edit_form(edit_form_html)
            
            if not form_data:
                self._show_error("フォーム解析に失敗しました")
                return
            
            # メタデータ（選択肢）を取得
            self._log_status("メタデータ（選択肢）を取得中...")
            metadata = self._fetch_theme_metadata(t_code)
            
            # 修正ダイアログを表示
            from qt_compat.widgets import QDialog
            from .portal_edit_dialog import PortalEditDialog
            
            dialog = PortalEditDialog(form_data, t_code, self.current_dataset_id, self.portal_client, self, metadata)
            
            if dialog.exec() == QDialog.Accepted:
                self._log_status("✅ データポータル修正が完了しました")
                self._show_info("データポータルの修正が完了しました")
                
                # JSONアップロード完了フラグを設定（修正も完了扱い）
                self.json_uploaded = True
                self._update_image_upload_button_state()
            else:
                self._log_status("データポータル修正をキャンセルしました")
                
        except ImportError:
            # ダイアログが未実装の場合は簡易版を表示
            self._show_edit_form_simple(t_code, self.current_dataset_id)
        except Exception as e:
            logger.error(f"データポータル修正エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_status(f"❌ データポータル修正エラー: {e}", error=True)
            self._show_error(f"データポータル修正エラー\n{e}")
    
    def _on_toggle_status(self):
        """ステータス変更処理（公開⇔非公開）"""
        if not self.current_dataset_id:
            self._show_warning("データセットが選択されていません")
            return
        
        if not self.current_status:
            self._show_warning("ステータス情報が取得できていません")
            return
        
        try:
            # t_codeを取得
            self._log_status("t_codeを取得中...")
            t_code = self._get_t_code_for_dataset(self.current_dataset_id)
            
            if not t_code:
                self._show_error(f"データセットID {self.current_dataset_id} に対応するt_codeが見つかりません")
                return
            
            self._log_status(f"t_code取得成功: {t_code}")
            
            # 確認ダイアログ
            if self.current_status == '公開済':
                action_text = "非公開にし"
                new_status_text = "非公開"
            else:
                action_text = "公開し"
                new_status_text = "公開済"
            
            reply = QMessageBox.question(
                self,
                "ステータス変更確認",
                f"データセット {self.current_dataset_id[:16]}... を{action_text}ますか？",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # ステータス変更実行
            self._log_status(f"ステータスを変更中: {self.current_status} → {new_status_text}")
            
            data = {
                'mode': 'theme',
                'mode2': 'open',  # 公開・非公開の切り替えは同じmode2
                't_code': t_code,
                'keyword': self.current_dataset_id,
                'search_inst': '',
                'search_license_level': '',
                'search_status': '',
                'page': '1'
            }
            
            logger.info(f"[TOGGLE_STATUS] ステータス変更: t_code={t_code}, current={self.current_status}")
            success, response = self.portal_client.post("main.php", data=data)
            
            if success and hasattr(response, 'text'):
                self._save_debug_response(f"toggle_status_{t_code}", response.text)
                logger.info(f"[TOGGLE_STATUS] レスポンスサイズ: {len(response.text)} bytes")
                
                # ステータス変更成功
                self._log_status(f"✅ ステータス変更完了: {new_status_text}")
                self._show_info(f"ステータスを{new_status_text}に変更しました")
                
                # ステータスを更新
                self.current_status = new_status_text
                
                # ボタン表示を更新
                if self.current_status == '公開済':
                    self.toggle_status_btn.setText("🔄 非公開にする")
                    self.toggle_status_btn.setToolTip("データポータルのエントリを非公開にします")
                else:
                    self.toggle_status_btn.setText("🔄 公開する")
                    self.toggle_status_btn.setToolTip("データポータルのエントリを公開します")
            else:
                logger.error(f"[TOGGLE_STATUS] ステータス変更失敗: {response}")
                self._show_error(f"ステータス変更に失敗しました\n{response}")
                
        except Exception as e:
            logger.error(f"ステータス変更エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self._log_status(f"❌ ステータス変更エラー: {e}", error=True)
            self._show_error(f"ステータス変更エラー\n{e}")
    
    def _open_edit_form(self, t_code: str, dataset_id: str) -> Tuple[bool, str]:
        """
        修正フォームを開く
        
        Args:
            t_code: テーマコード
            dataset_id: データセットID
        
        Returns:
            Tuple[bool, str]: (成功フラグ, HTMLまたはエラーメッセージ)
        """
        try:
            data = {
                'mode': 'theme',
                'mode2': 'change',
                't_code': t_code,
                'keyword': dataset_id,
                'search_inst': '',
                'search_license_level': '',
                'search_status': '',
                'page': '1'
            }
            
            logger.info(f"[EDIT_FORM] 修正画面を開く: t_code={t_code}")
            success, response = self.portal_client.post("main.php", data=data)
            
            if not success or not hasattr(response, 'text'):
                return False, "修正画面の取得に失敗しました"
            
            # デバッグ保存
            self._save_debug_response(f"edit_form_{t_code}", response.text)
            logger.info(f"[EDIT_FORM] レスポンスサイズ: {len(response.text)} bytes")
            
            return True, response.text
            
        except Exception as e:
            logger.error(f"修正フォーム取得エラー: {e}")
            return False, str(e)
    
    def _fetch_theme_metadata(self, t_code: str) -> dict:
        """
        theme APIからメタデータ（選択肢）を取得
        
        Args:
            t_code: テーマコード
        
        Returns:
            dict: メタデータ（選択肢情報）
        """
        try:
            data = {
                'mode': 'theme',
                'mode2': 'change',
                't_code': t_code,
                'keyword': '',
                'search_inst': '',
                'search_license_level': '',
                'search_status': '',
                'page': '1'
            }
            
            logger.info(f"[THEME_META] メタデータ取得: t_code={t_code}")
            success, response = self.portal_client.post("main.php", data=data)
            
            if not success or not hasattr(response, 'text'):
                logger.error("[THEME_META] メタデータ取得失敗")
                return {}
            
            # HTMLからメタデータを抽出
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            metadata = {}
            
            # ライセンス (t_license) - ラジオボタン
            license_radios = soup.find_all('input', {'type': 'radio', 'name': 't_license'})
            if license_radios:
                metadata['t_license'] = {
                    'type': 'radio',
                    'options': [{'value': r.get('value', ''), 'label': self._extract_label(r, soup)} for r in license_radios]
                }
            
            # 重要技術領域（主） (main_mita_code_array) - チェックボックス
            main_area_checkboxes = soup.find_all('input', {'type': 'checkbox', 'name': 'main_mita_code_array[]'})
            if main_area_checkboxes:
                metadata['main_mita_code_array[]'] = {
                    'type': 'checkbox',
                    'options': [{'value': cb.get('value', ''), 'label': self._extract_label(cb, soup)} for cb in main_area_checkboxes]
                }
            
            # 重要技術領域（副） (sub_mita_code_array) - チェックボックス
            sub_area_checkboxes = soup.find_all('input', {'type': 'checkbox', 'name': 'sub_mita_code_array[]'})
            if sub_area_checkboxes:
                metadata['sub_mita_code_array[]'] = {
                    'type': 'checkbox',
                    'options': [{'value': cb.get('value', ''), 'label': self._extract_label(cb, soup)} for cb in sub_area_checkboxes]
                }
            
            # 横断技術領域 (mcta_code_array) - チェックボックス
            cross_area_checkboxes = soup.find_all('input', {'type': 'checkbox', 'name': 'mcta_code_array[]'})
            if cross_area_checkboxes:
                metadata['mcta_code_array[]'] = {
                    'type': 'checkbox',
                    'options': [{'value': cb.get('value', ''), 'label': self._extract_label(cb, soup)} for cb in cross_area_checkboxes]
                }
            
            # 設備分類 (mec_code_array) - 編集ページから取得またはキャッシュから読み込み
            equipment_checkboxes = soup.find_all('input', {'type': 'checkbox', 'name': 'mec_code_array[]'})
            if equipment_checkboxes:
                metadata['mec_code_array[]'] = {
                    'type': 'checkbox',
                    'options': [{'value': cb.get('value', ''), 'label': self._extract_label(cb, soup)} for cb in equipment_checkboxes]
                }
                logger.info(f"[THEME_META] 設備分類をHTMLから取得: {len(equipment_checkboxes)}項目")
            else:
                # HTMLから取得できない場合、編集ページから取得
                logger.info("[THEME_META] 設備分類を編集ページから取得")
                from classes.data_portal.core.master_data import MasterDataManager
                master_manager = MasterDataManager(self.portal_client)
                success, eqp_data = master_manager.fetch_equipment_master_from_edit_page()
                
                if success and eqp_data:
                    metadata['mec_code_array[]'] = {
                        'type': 'checkbox',
                        'options': [{'value': code, 'label': name} for code, name in eqp_data.items()]
                    }
                    logger.info(f"[THEME_META] 設備分類: {len(eqp_data)}項目")
            
            # マテリアルインデックス (mmi_code_array) - マスターデータから取得
            if not soup.find_all('input', {'type': 'checkbox', 'name': 'mmi_code_array[]'}):
                logger.info("[THEME_META] マテリアルインデックスをマスターデータから取得")
                from classes.data_portal.core.master_data import MasterDataManager
                master_manager = MasterDataManager(self.portal_client)
                success, mi_data = master_manager.load_material_index_master()
                
                if success and mi_data:
                    metadata['mmi_code_array[]'] = {
                        'type': 'checkbox',
                        'options': [{'value': code, 'label': name} for code, name in mi_data.items()]
                    }
                    logger.info(f"[THEME_META] マテリアルインデックス: {len(mi_data)}項目")
            else:
                material_checkboxes = soup.find_all('input', {'type': 'checkbox', 'name': 'mmi_code_array[]'})
                metadata['mmi_code_array[]'] = {
                    'type': 'checkbox',
                    'options': [{'value': cb.get('value', ''), 'label': self._extract_label(cb, soup)} for cb in material_checkboxes]
                }
                logger.info(f"[THEME_META] マテリアルインデックスをHTMLから取得: {len(material_checkboxes)}項目")
            
            # タグ (mt_code_array) - マスターデータから取得
            if not soup.find_all('input', {'type': 'checkbox', 'name': 'mt_code_array[]'}):
                logger.info("[THEME_META] タグをマスターデータから取得")
                from classes.data_portal.core.master_data import MasterDataManager
                master_manager = MasterDataManager(self.portal_client)
                success, tag_data = master_manager.load_tag_master()
                
                if success and tag_data:
                    metadata['mt_code_array[]'] = {
                        'type': 'checkbox',
                        'options': [{'value': code, 'label': name} for code, name in tag_data.items()]
                    }
                    logger.info(f"[THEME_META] タグ: {len(tag_data)}項目")
            else:
                tag_checkboxes = soup.find_all('input', {'type': 'checkbox', 'name': 'mt_code_array[]'})
                metadata['mt_code_array[]'] = {
                    'type': 'checkbox',
                    'options': [{'value': cb.get('value', ''), 'label': self._extract_label(cb, soup)} for cb in tag_checkboxes]
                }
                logger.info(f"[THEME_META] タグをHTMLから取得: {len(tag_checkboxes)}項目")
            
            logger.info(f"[THEME_META] メタデータ取得完了: {len(metadata)}項目")
            return metadata
            
        except Exception as e:
            logger.error(f"メタデータ取得エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
    
    def _parse_edit_form(self, html: str) -> dict:
        """
        修正フォームのHTMLを解析してフィールド情報を抽出
        
        Args:
            html: フォームHTML
        
        Returns:
            dict: フォームデータ
        """
        try:
            from bs4 import BeautifulSoup
            import re
            
            soup = BeautifulSoup(html, 'html.parser')
            form_data = {}
            
            # 全てのinput, select, textareaを取得
            for elem in soup.find_all(['input', 'select', 'textarea']):
                name = elem.get('name')
                if not name:
                    continue
                
                if elem.name == 'input':
                    input_type = elem.get('type', 'text')
                    if input_type == 'hidden':
                        form_data[name] = {'type': 'hidden', 'value': elem.get('value', '')}
                    elif input_type == 'radio':
                        # ラジオボタン: チェックされているものの値を取得
                        if elem.has_attr('checked'):
                            form_data[name] = {
                                'type': 'radio',
                                'value': elem.get('value', ''),
                                'label': self._extract_label(elem, soup)
                            }
                        # 既にラジオボタンのデータがある場合はスキップ
                        elif name in form_data:
                            continue
                    elif input_type in ['text', 'number', 'datetime-local', 'date', 'time']:
                        form_data[name] = {
                            'type': input_type,
                            'value': elem.get('value', ''),
                            'label': self._extract_label(elem, soup)
                        }
                    elif input_type == 'checkbox':
                        # チェックボックス: 配列として管理
                        if name not in form_data:
                            form_data[name] = {
                                'type': 'checkbox_array',
                                'values': [],
                                'label': self._extract_label(elem, soup)
                            }
                        value = elem.get('value', '')
                        is_checked = elem.has_attr('checked')
                        form_data[name]['values'].append({'value': value, 'checked': is_checked})
                elif elem.name == 'select':
                    options = []
                    selected_value = ''
                    for option in elem.find_all('option'):
                        opt_value = option.get('value', '')
                        opt_text = option.get_text(strip=True)
                        is_selected = option.has_attr('selected')
                        options.append({'value': opt_value, 'text': opt_text, 'selected': is_selected})
                        if is_selected:
                            selected_value = opt_value
                    
                    form_data[name] = {
                        'type': 'select',
                        'value': selected_value,
                        'options': options,
                        'label': self._extract_label(elem, soup)
                    }
                elif elem.name == 'textarea':
                    form_data[name] = {
                        'type': 'textarea',
                        'value': elem.get_text(strip=True),
                        'label': self._extract_label(elem, soup)
                    }
            
            logger.info(f"[PARSE_FORM] フォームフィールド数: {len(form_data)}")
            return form_data
            
        except Exception as e:
            logger.error(f"フォーム解析エラー: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {}
    
    def _extract_label(self, elem, soup) -> str:
        """要素のラベルを抽出"""
        try:
            # ラジオボタン/チェックボックス用: IDで関連付けられたlabelを探す
            elem_id = elem.get('id')
            if elem_id:
                label = soup.find('label', {'for': elem_id})
                if label:
                    # labelのテキストを取得（画像タグなどは除外）
                    label_text = label.get_text(strip=True)
                    return label_text
            
            # 親のthタグを探す
            parent = elem.find_parent('td')
            if parent:
                prev_th = parent.find_previous_sibling('th')
                if prev_th:
                    return prev_th.get_text(strip=True)
            
            # labelタグを探す（フォールバック）
            label = elem.find_previous('label')
            if label:
                return label.get_text(strip=True)
            
            return ""
        except:
            return ""
    
    def _show_edit_form_simple(self, t_code: str, dataset_id: str):
        """簡易版修正フォーム（ダイアログ未実装時のフォールバック）"""
        msg = (
            f"データポータル修正機能\n\n"
            f"データセットID: {dataset_id}\n"
            f"t_code: {t_code}\n\n"
            f"修正ダイアログは実装中です。\n"
            f"現在はログに詳細を出力しています。"
        )
        self._show_info(msg)
