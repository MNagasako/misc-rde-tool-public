"""オフラインモード設定タブ。"""

from __future__ import annotations

import logging

from classes.managers.app_config_manager import get_config_manager
from classes.core.offline_mode import (
    OFFLINE_SITE_AI_API,
    OFFLINE_SITE_DATA_PORTAL,
    OFFLINE_SITE_DATA_PORTAL_TEST,
    OFFLINE_SITE_RDE,
    set_offline_state,
)

from qt_compat.widgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QCheckBox,
    QPushButton,
    QMessageBox,
)
from classes.theme import get_color, ThemeKey

logger = logging.getLogger(__name__)


class OfflineModeTab(QWidget):
    """設定ダイアログ向けのオフライン設定UI。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_manager = get_config_manager()
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("オフラインモード設定")
        title.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)};")
        layout.addWidget(title)

        desc = QLabel(
            "オフラインモードを有効化すると、選択した外部サイトへのアクセスを抑止します。\n"
            "キャッシュ済みデータの閲覧やローカル操作を優先する運用向けです。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        layout.addWidget(desc)

        common_group = QGroupBox("基本設定")
        common_group.setStyleSheet(
            f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
            """
        )
        common_layout = QVBoxLayout(common_group)

        self.offline_enabled_checkbox = QCheckBox("オフラインモードを有効にする")
        self.offline_enabled_checkbox.toggled.connect(self._update_site_checkboxes_state)
        self.offline_enabled_checkbox.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_PRIMARY)};")
        common_layout.addWidget(self.offline_enabled_checkbox)

        layout.addWidget(common_group)

        site_group = QGroupBox("サイト別オフライン指定")
        site_group.setStyleSheet(
            f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
            """
        )
        site_layout = QVBoxLayout(site_group)

        self.site_checkboxes = {
            OFFLINE_SITE_RDE: QCheckBox("RDE (*.nims.go.jp)"),
            OFFLINE_SITE_DATA_PORTAL: QCheckBox("データポータル (nanonet.go.jp / *.nanonet.go.jp)"),
            OFFLINE_SITE_DATA_PORTAL_TEST: QCheckBox("データポータル テストサイト（設定されている場合）"),
            OFFLINE_SITE_AI_API: QCheckBox("AI API (OpenAI / Gemini / Local LLM)"),
        }

        for checkbox in self.site_checkboxes.values():
            checkbox.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_PRIMARY)};")
            site_layout.addWidget(checkbox)

        site_note = QLabel("※ オフライン指定したサイトに依存する機能のみ利用不可になります。")
        site_note.setWordWrap(True)
        site_note.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)};")
        site_layout.addWidget(site_note)

        layout.addWidget(site_group)

        btn_layout = QHBoxLayout()
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self.save_settings)
        self.save_button.setStyleSheet(
            f"""
            QPushButton {{
                padding: 6px 14px;
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)};
            }}
            """
        )
        btn_layout.addWidget(self.save_button)
        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

        layout.addStretch(1)

    def _load_settings(self):
        enabled = bool(self.config_manager.get("offline.enabled", False))
        site_states = self.config_manager.get("offline.sites", {})

        self.offline_enabled_checkbox.setChecked(enabled)
        for site_key, checkbox in self.site_checkboxes.items():
            checkbox.setChecked(bool(site_states.get(site_key, True)))

        self._update_site_checkboxes_state()

    def _collect_site_states(self):
        return {site_key: bool(checkbox.isChecked()) for site_key, checkbox in self.site_checkboxes.items()}

    def _update_site_checkboxes_state(self):
        enabled = bool(self.offline_enabled_checkbox.isChecked())
        for checkbox in self.site_checkboxes.values():
            checkbox.setEnabled(enabled)

    def apply_settings(self):
        self._save(show_message=False)

    def save_settings(self):
        self._save(show_message=True)

    def _save(self, show_message: bool):
        try:
            enabled = bool(self.offline_enabled_checkbox.isChecked())
            site_states = self._collect_site_states()
            if not set_offline_state(enabled, site_states, persist=True):
                raise RuntimeError("設定ファイルの保存に失敗しました")

            self._refresh_main_window_offline_state()

            if show_message:
                QMessageBox.information(self, "保存完了", "オフラインモード設定を保存しました。")
        except Exception as e:
            logger.error("オフライン設定の保存失敗: %s", e, exc_info=True)
            if show_message:
                QMessageBox.warning(self, "保存失敗", f"オフライン設定の保存に失敗しました: {e}")

    def _refresh_main_window_offline_state(self):
        try:
            top = self.window() if hasattr(self, "window") else None
            ui_controller = getattr(top, "ui_controller", None)
            if ui_controller is None:
                return

            ui_controller.set_buttons_enabled_except_login_settings(True)
            if hasattr(ui_controller, "_update_offline_status_banner"):
                ui_controller._update_offline_status_banner()
        except Exception as e:
            logger.debug("オフライン保存後のUI更新に失敗: %s", e)
