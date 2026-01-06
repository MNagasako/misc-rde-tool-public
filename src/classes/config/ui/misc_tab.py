"""
MISC（その他）タブ - ARIM RDE Tool
その他の便利機能を集約

Phase2-2: 設定メニューMISCタブ追加
"""

import sys
import os
import logging
from pathlib import Path

from config.common import REVISION

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
        QLabel, QPushButton, QMessageBox, QCheckBox
    )
    from qt_compat.core import Qt
    from classes.theme import get_color, ThemeKey
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass

# ログ設定
logger = logging.getLogger(__name__)

class MiscTab(QWidget):
    """MISC（その他）タブ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # タイトル
        title_label = QLabel("その他の便利機能")
        title_label.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {get_color(ThemeKey.TEXT_PRIMARY)};")
        layout.addWidget(title_label)

        # 起動オプション
        startup_group = self.create_startup_group()
        layout.addWidget(startup_group)

        # アプリ更新
        update_group = self.create_update_group()
        layout.addWidget(update_group)
        
        # ディレクトリ操作グループ
        dir_group = self.create_directory_group()
        layout.addWidget(dir_group)
        
        # スペーサー（将来の拡張用）
        layout.addStretch(1)

    def create_update_group(self):
        """アプリ更新（GitHub Releases 配布）"""
        group = QGroupBox("アプリ更新")
        group.setStyleSheet(
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

        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        current_label = QLabel(f"現在のバージョン: {REVISION}")
        current_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: normal;"
        )
        layout.addWidget(current_label)

        info_label = QLabel(
            "配布用GitHubリポジトリ（main/latest.json）から更新を確認し、\n"
            "更新があればインストーラをダウンロードしてサイレント実行します。\n"
            "（ダウンロード後は sha256 を必ず検証します）"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 9pt; font-weight: normal;"
        )
        layout.addWidget(info_label)

        btn_layout = QHBoxLayout()

        check_btn = QPushButton("更新を確認")
        check_btn.clicked.connect(self.check_for_update)
        check_btn.setStyleSheet(
            f"""
            QPushButton {{
                padding: 6px 14px;
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
            }}
            """
        )
        btn_layout.addWidget(check_btn)

        layout.addLayout(btn_layout)
        layout.addStretch(1)
        return group

    def check_for_update(self):
        """手動の更新確認→希望があればDL+検証+インストーラ実行"""
        try:
            from classes.core.app_updater import (
                check_update,
                download,
                get_default_download_path,
                run_installer_and_restart,
                verify_sha256,
            )

            has_update, latest_version, url, sha256, updated_at = check_update(REVISION)
            updated_at_text = updated_at or "不明"
            if not has_update:
                QMessageBox.information(
                    self,
                    "更新確認",
                    "現在のバージョンは最新です。\n\n"
                    f"現在: {REVISION}\n"
                    f"latest.json: {latest_version or REVISION}\n"
                    f"更新日時: {updated_at_text}",
                )
                return

            reply = QMessageBox.question(
                self,
                "更新があります",
                "新しいバージョンが利用可能です。\n\n"
                f"現在: {REVISION}\n"
                f"latest.json: {latest_version}\n"
                f"更新日時: {updated_at_text}\n\n"
                "インストーラをダウンロードして更新しますか？\n\n"
                "（更新完了後は自動で再起動します）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return

            dst = get_default_download_path(latest_version)
            QMessageBox.information(self, "更新", "ダウンロードを開始します。完了までお待ちください。")
            download(url, dst)

            if not verify_sha256(dst, sha256):
                QMessageBox.warning(
                    self,
                    "更新失敗",
                    "sha256検証に失敗しました。\n安全のためインストーラは実行しません。",
                )
                return

            # 実行（この関数内でアプリ終了→更新完了後に再起動）
            run_installer_and_restart(dst)

        except Exception as e:
            logger.error("更新確認/実行でエラー: %s", e, exc_info=True)
            QMessageBox.warning(self, "更新エラー", f"更新処理に失敗しました: {e}")

    def create_startup_group(self):
        """起動関連オプション"""
        group = QGroupBox("起動")
        group.setStyleSheet(
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

        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        self.splash_checkbox = QCheckBox("起動時にスプラッシュを表示する（既定: 表示）")
        self.splash_checkbox.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: normal;"
        )
        self.splash_checkbox.setToolTip(
            "環境変数 RDE_DISABLE_SPLASH_SCREEN / RDE_ENABLE_SPLASH_SCREEN が指定されている場合は、そちらが優先されます。"
        )
        layout.addWidget(self.splash_checkbox)

        info_label = QLabel(
            "この設定は次回起動時から有効になります。\n"
            "スプラッシュ画面はアプリ起動時に表示されるロゴ画面です。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 9pt; font-weight: normal;"
        )
        layout.addWidget(info_label)

        btn_layout = QHBoxLayout()
        apply_btn = QPushButton("保存")
        apply_btn.setStyleSheet(
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
        apply_btn.clicked.connect(self.save_startup_settings)
        btn_layout.addWidget(apply_btn)
        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

        # 初期値読み込み
        self.load_startup_settings()

        return group

    def load_startup_settings(self):
        """起動関連設定の読み込み"""
        try:
            from classes.managers.app_config_manager import get_config_manager

            cfg = get_config_manager()
            enabled = bool(cfg.get("app.enable_splash_screen", True))
            self.splash_checkbox.setChecked(enabled)
        except Exception as e:
            logger.debug("スプラッシュ設定の読み込みに失敗: %s", e)
            try:
                self.splash_checkbox.setChecked(True)
            except Exception:
                pass

    def save_startup_settings(self):
        """起動関連設定の保存"""
        try:
            from classes.managers.app_config_manager import get_config_manager

            cfg = get_config_manager()
            cfg.set("app.enable_splash_screen", bool(self.splash_checkbox.isChecked()))
            if not cfg.save():
                raise RuntimeError("設定ファイルの保存に失敗しました")

            QMessageBox.information(self, "保存完了", "起動設定を保存しました。\n次回起動時から反映されます。")
        except Exception as e:
            QMessageBox.warning(self, "保存失敗", f"起動設定の保存に失敗しました: {e}")
        
    def create_directory_group(self):
        """ディレクトリ操作グループ"""
        group = QGroupBox("ディレクトリ操作")
        group.setStyleSheet(f"""
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
        """)
        
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        
        # インストールディレクトリを開くボタン
        install_dir_layout = QHBoxLayout()
        
        install_dir_label = QLabel("アプリケーションのインストール先:")
        install_dir_label.setStyleSheet("font-weight: normal;")
        install_dir_layout.addWidget(install_dir_label)
        
        open_install_dir_btn = QPushButton("📁 インストールディレクトリを開く")
        open_install_dir_btn.setToolTip("アプリケーションがインストールされているディレクトリをエクスプローラーで開きます")
        open_install_dir_btn.clicked.connect(self.open_install_directory)
        open_install_dir_btn.setStyleSheet(f"""
            QPushButton {{
                padding: 8px 15px;
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:pressed {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED)};
            }}
        """)
        install_dir_layout.addWidget(open_install_dir_btn)
        install_dir_layout.addStretch()
        
        layout.addLayout(install_dir_layout)
        
        # 説明ラベル
        info_label = QLabel(
            "インストールディレクトリには、アプリケーションの実行ファイル、\n"
            "設定ファイル、ログファイルなどが保存されています。"
        )
        info_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 9pt; font-weight: normal;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        return group
        
    def open_install_directory(self):
        """インストールディレクトリを開く"""
        try:
            from config.common import get_base_dir
            # アプリケーションのルートディレクトリを取得
            if getattr(sys, 'frozen', False):
                # PyInstallerでバイナリ化されている場合
                app_dir = Path(sys.executable).parent
            else:
                # 開発環境（ソースから実行）の場合
                app_dir = Path(get_base_dir())
                
            logger.info(f"インストールディレクトリを開く: {app_dir}")
            
            # OSに応じてディレクトリを開く
            if sys.platform == 'win32':
                os.startfile(str(app_dir))
            elif sys.platform == 'darwin':
                os.system(f'open "{app_dir}"')
            else:
                os.system(f'xdg-open "{app_dir}"')
                
            logger.info("インストールディレクトリを開きました")
            
        except Exception as e:
            logger.error(f"インストールディレクトリを開く際にエラーが発生: {e}")
            import traceback
            traceback.print_exc()
            
            QMessageBox.critical(
                self,
                "エラー",
                f"ディレクトリを開けませんでした:\n{str(e)}"
            )
