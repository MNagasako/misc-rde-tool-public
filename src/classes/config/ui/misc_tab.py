"""
MISC（その他）タブ - ARIM RDE Tool
その他の便利機能を集約

Phase2-2: 設定メニューMISCタブ追加
"""

import sys
import os
import logging
import threading
from pathlib import Path

from config.common import REVISION
from classes.managers.app_config_manager import get_config_manager

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
        QLabel, QPushButton, QMessageBox, QCheckBox, QProgressDialog
    )
    from qt_compat.core import Qt, QTimer, QObject, Signal, Slot, QThread
    from classes.theme import get_color, ThemeKey
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass

# ログ設定
logger = logging.getLogger(__name__)

# QThread は親Widget破棄に巻き込まれると不安定になり得るため、
# fire-and-forget用途ではモジュール側で参照を保持して安全に完了させる。
_ACTIVE_UPDATE_CHECK_THREADS = set()


class _UpdateCheckProgressStub(QObject):
    """pytest実行時用の軽量な進捗ダミー。

    Windows/PySide6 の widget スイートでは、ネイティブウィンドウ（QProgressDialog 等）を
    大量に作ると稀にプロセスがネイティブクラッシュすることがある。
    テストで検証したいのは「キャンセル/完了の配線」であり、実ウィンドウは不要なため
    QObject ベースのスタブに置き換える。
    """

    canceled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def setWindowTitle(self, _title: str) -> None:
        return

    def setLabelText(self, _text: str) -> None:
        return

    def setRange(self, _minimum: int, _maximum: int) -> None:
        return

    def setMinimumDuration(self, _ms: int) -> None:
        return

    def setWindowModality(self, _modality) -> None:
        return

    def setCancelButtonText(self, _text: str) -> None:
        return

    def setAttribute(self, *_args, **_kwargs) -> None:
        return

    def show(self) -> None:
        return

    def hide(self) -> None:
        return

    def close(self) -> None:
        return

    def deleteLater(self) -> None:
        return

    def cancel(self) -> None:
        try:
            self.canceled.emit()
        except Exception:
            pass


class _UpdateCheckWorker(QObject):
    result_ready = Signal(object)

    def __init__(self, check_update_func, current_version: str, parent=None):
        super().__init__(parent)
        self._check_update = check_update_func
        self._current_version = current_version

    @Slot()
    def run(self) -> None:
        try:
            result = self._check_update(self._current_version)
        except Exception as exc:
            result = exc
        self.result_ready.emit(result)

class MiscTab(QWidget):
    """MISC（その他）タブ"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._update_in_progress = False
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

        # メインメニュー表示
        menu_group = self.create_menu_group()
        layout.addWidget(menu_group)
        
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
            "更新があればインストーラをダウンロードします。\n"
            "（ダウンロード後は sha256 を必ず検証します。検証成功後、保存先を開きます）"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 9pt; font-weight: normal;"
        )
        layout.addWidget(info_label)

        btn_layout = QHBoxLayout()

        self._update_check_btn = QPushButton("更新を確認")
        self._update_check_btn.clicked.connect(self.check_for_update)
        self._update_check_btn.setStyleSheet(
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
        btn_layout.addWidget(self._update_check_btn)

        layout.addLayout(btn_layout)
        layout.addStretch(1)
        return group

    def create_menu_group(self):
        """メインメニュー表示設定"""
        group = QGroupBox("メインメニュー")
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

        info_label = QLabel(
            "メインメニューの一部ボタンを表示/非表示にできます。\n"
            "※『データ取得2』『AIテスト2』は常時表示です。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-size: 9pt; font-weight: normal;"
        )
        layout.addWidget(info_label)

        self.menu_show_data_fetch_checkbox = QCheckBox("メインメニューに『データ取得』を表示する（既定: 非表示）")
        self.menu_show_data_fetch_checkbox.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: normal;"
        )
        layout.addWidget(self.menu_show_data_fetch_checkbox)

        self.menu_show_ai_test_checkbox = QCheckBox("メインメニューに『AIテスト』を表示する（既定: 非表示）")
        self.menu_show_ai_test_checkbox.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: normal;"
        )
        layout.addWidget(self.menu_show_ai_test_checkbox)

        self.menu_show_request_analyzer_checkbox = QCheckBox("メインメニューに『リクエスト解析』を表示する（既定: 非表示）")
        self.menu_show_request_analyzer_checkbox.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: normal;"
        )
        layout.addWidget(self.menu_show_request_analyzer_checkbox)

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
        apply_btn.clicked.connect(self.save_menu_settings)
        btn_layout.addWidget(apply_btn)
        btn_layout.addStretch(1)
        layout.addLayout(btn_layout)

        self.load_menu_settings()
        return group

    def load_menu_settings(self):
        """メインメニュー表示設定の読み込み"""
        try:
            cfg = get_config_manager()
            show_data_fetch = bool(cfg.get("app.menu.show_data_fetch", False))
            show_ai_test = bool(cfg.get("app.menu.show_ai_test", False))
            show_request_analyzer = bool(cfg.get("app.menu.show_request_analyzer", False))
            self.menu_show_data_fetch_checkbox.setChecked(show_data_fetch)
            self.menu_show_ai_test_checkbox.setChecked(show_ai_test)
            self.menu_show_request_analyzer_checkbox.setChecked(show_request_analyzer)
        except Exception as e:
            logger.debug("メインメニュー設定の読み込みに失敗: %s", e)
            try:
                self.menu_show_data_fetch_checkbox.setChecked(False)
                self.menu_show_ai_test_checkbox.setChecked(False)
                self.menu_show_request_analyzer_checkbox.setChecked(False)
            except Exception:
                pass

    def save_menu_settings(self):
        """メインメニュー表示設定の保存"""
        try:
            cfg = get_config_manager()
            cfg.set("app.menu.show_data_fetch", bool(self.menu_show_data_fetch_checkbox.isChecked()))
            cfg.set("app.menu.show_ai_test", bool(self.menu_show_ai_test_checkbox.isChecked()))
            cfg.set("app.menu.show_request_analyzer", bool(self.menu_show_request_analyzer_checkbox.isChecked()))
            if not cfg.save():
                raise RuntimeError("設定ファイルの保存に失敗しました")

            QMessageBox.information(
                self,
                "保存完了",
                "メインメニュー設定を保存しました。\n次回起動時から反映されます。",
            )
        except Exception as e:
            QMessageBox.warning(self, "保存失敗", f"メインメニュー設定の保存に失敗しました: {e}")

    def check_for_update(self):
        """手動の更新確認→希望があればDL+検証+インストーラ実行（進捗表示/非同期）"""
        try:
            from classes.core import app_updater as app_updater_mod

            is_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))

            if self._update_in_progress:
                return
            self._update_in_progress = True

            if hasattr(self, "_update_check_btn"):
                self._update_check_btn.setEnabled(False)

            cancelled = {"v": False}
            progress = _UpdateCheckProgressStub(self) if is_pytest else QProgressDialog(self)
            # テストでは QApplication.topLevelWidgets() の走査が不安定化要因になり得るため、
            # 進捗ダイアログをインスタンス変数として保持して参照可能にする。
            self._update_check_progress = progress
            progress.setWindowTitle("更新確認")
            progress.setLabelText("更新情報（latest.json）を取得中...")
            progress.setRange(0, 0)  # indeterminate
            progress.setMinimumDuration(0 if is_pytest else 300)
            progress.setWindowModality(Qt.NonModal if is_pytest else Qt.WindowModal)
            progress.setCancelButtonText("キャンセル")
            try:
                progress.setAttribute(Qt.WA_DeleteOnClose, True)
            except Exception:
                pass

            def _on_cancel():
                cancelled["v"] = True
                # キャンセル後に worker が完了してもUIへ戻らないようにする
                try:
                    w = getattr(self, "_update_check_worker", None)
                    slot = getattr(self, "_update_check_dispatch_slot", None)
                    if w is not None and slot is not None:
                        w.result_ready.disconnect(slot)
                except Exception:
                    pass
                _finish_ui(enable_button=True)

            progress.canceled.connect(_on_cancel)
            # pytest（widgetスイート）ではOSネイティブウィンドウ生成が大量に積み上がると
            # PySide6/Windows環境で不安定化（クラッシュ/突然のプロセス終了）し得る。
            # テストは進捗表示自体ではなく完了/キャンセルの配線を検証したいので、
            # 進捗ダイアログは生成するが表示は行わない。
            if not is_pytest:
                progress.show()

            def _finish_ui(enable_button: bool = True) -> None:
                # watchdog / invoke タイマーが残ると、長時間のwidgetスイートで
                # 破棄済みUIに触れて不安定化する可能性があるので必ず止める
                try:
                    t = getattr(self, "_update_check_watchdog_timer", None)
                    if t is not None:
                        t.stop()
                except Exception:
                    pass
                try:
                    t = getattr(self, "_update_check_invoke_timer", None)
                    if t is not None:
                        t.stop()
                except Exception:
                    pass
                # pytest中は deleteLater() による非同期破棄が長いwidgetスイートで
                # Qtネイティブクラッシュの引き金になり得るため、親(self)に寿命管理を委ねる。
                if is_pytest:
                    try:
                        progress.hide()
                    except Exception:
                        pass
                else:
                    try:
                        progress.close()
                    except Exception:
                        pass
                    try:
                        progress.deleteLater()
                    except Exception:
                        pass
                try:
                    self._update_check_progress = None
                except Exception:
                    pass
                if enable_button and hasattr(self, "_update_check_btn"):
                    self._update_check_btn.setEnabled(True)
                self._update_in_progress = False
                # watchdogの誤発火（正常完了後のタイムアウト通知）を防ぐ
                cancelled["v"] = True

            def _timeout_watchdog() -> None:
                if cancelled["v"]:
                    return
                # まだ進行中ならタイムアウト扱い
                cancelled["v"] = True
                _finish_ui(enable_button=True)
                if not is_pytest:
                    QMessageBox.warning(
                        self,
                        "更新確認",
                        "更新情報の取得がタイムアウトしました。\n"
                        "ネットワーク/プロキシ設定をご確認のうえ、再試行してください。",
                    )

            # 30秒で強制的に終わらせる（HTTPが戻らない環境向け）
            # singleShot(receiver, callable) は環境によって不安定になることがあるため
            # 明示的なQTimerインスタンスで寿命を管理する。
            try:
                t = getattr(self, "_update_check_watchdog_timer", None)
                if t is not None:
                    t.stop()
            except Exception:
                pass
            self._update_check_watchdog_timer = QTimer(self)
            self._update_check_watchdog_timer.setSingleShot(True)
            self._update_check_watchdog_timer.timeout.connect(_timeout_watchdog)
            self._update_check_watchdog_timer.start(30_000)

            def _handle_result(payload: object) -> None:
                try:
                    if cancelled["v"]:
                        return

                    if isinstance(payload, Exception):
                        _finish_ui(enable_button=True)
                        QMessageBox.warning(self, "更新エラー", f"更新確認に失敗しました: {payload}")
                        return

                    has_update, latest_version, url, sha256, updated_at = payload
                    _finish_ui(enable_button=True)

                    # widgetテストでは QMessageBox を出さずに完了させる（Windows/PySide6での不安定化を避ける）
                    if is_pytest:
                        return

                    # latest.json取得失敗（check_updateは例外を握りつぶして空文字を返す）
                    if not latest_version or not url or not sha256:
                        QMessageBox.warning(
                            self,
                            "更新確認",
                            "更新情報の取得に失敗しました。\n"
                            "ネットワーク/プロキシ設定をご確認のうえ、時間をおいて再試行してください。",
                        )
                        return

                    updated_at_text = updated_at or "不明"
                    if not has_update:
                        try:
                            from classes.core.app_updater import is_same_version
                        except Exception:
                            is_same_version = None

                        release_url = "https://github.com/MNagasako/misc-rde-tool-public/releases/latest"

                        # latest.json が現在版と同一の場合でも、再インストール導線を用意する。
                        if callable(is_same_version) and is_same_version(REVISION, latest_version):
                            box = QMessageBox(self)
                            box.setIcon(QMessageBox.Information)
                            box.setWindowTitle("更新確認")
                            box.setText("現在のバージョンは最新です。")
                            box.setInformativeText(
                                f"現在: {REVISION}\n"
                                f"latest.json: {latest_version}\n"
                                f"更新日時: {updated_at_text}\n\n"
                                "同一バージョンを再ダウンロードして、再インストールすることもできます。\n\n"
                                f"リリースページ: {release_url}"
                            )

                            reinstall_btn = box.addButton("同一版を再インストール", QMessageBox.AcceptRole)
                            open_site_btn = box.addButton("更新サイトを開く", QMessageBox.ActionRole)
                            close_btn = box.addButton("閉じる", QMessageBox.RejectRole)
                            box.setDefaultButton(close_btn)
                            box.exec()

                            if box.clickedButton() == open_site_btn:
                                try:
                                    from classes.core.app_update_ui import open_url_in_browser

                                    open_url_in_browser(release_url)
                                except Exception:
                                    pass
                            elif box.clickedButton() == reinstall_btn:
                                self._download_and_install(url=url, version=latest_version, sha256=sha256)
                            return

                        # 更新が無い場合でも、最新版の再インストール導線とリンクを出す。
                        box = QMessageBox(self)
                        box.setIcon(QMessageBox.Information)
                        box.setWindowTitle("更新確認")
                        box.setText("現在のバージョンは最新です。")
                        box.setInformativeText(
                            f"現在: {REVISION}\n"
                            f"latest.json: {latest_version}\n"
                            f"更新日時: {updated_at_text}\n\n"
                            "最新版を再ダウンロードして再インストールすることもできます。\n\n"
                            f"リリースページ: {release_url}"
                        )
                        reinstall_btn = box.addButton("最新版を再インストール", QMessageBox.AcceptRole)
                        open_site_btn = box.addButton("更新サイトを開く", QMessageBox.ActionRole)
                        close_btn = box.addButton("閉じる", QMessageBox.RejectRole)
                        box.setDefaultButton(close_btn)
                        box.exec()
                        if box.clickedButton() == open_site_btn:
                            try:
                                from classes.core.app_update_ui import open_url_in_browser

                                open_url_in_browser(release_url)
                            except Exception:
                                pass
                        elif box.clickedButton() == reinstall_btn:
                            self._download_and_install(url=url, version=latest_version, sha256=sha256)
                        return

                    release_url = "https://github.com/MNagasako/misc-rde-tool-public/releases/latest"

                    box = QMessageBox(self)
                    box.setIcon(QMessageBox.Question)
                    box.setWindowTitle("更新があります")
                    box.setTextFormat(Qt.RichText)
                    box.setText(
                        "新しいバージョンが利用可能です。<br><br>"
                        f"現在: {REVISION}<br>"
                        f"latest.json: {latest_version}<br>"
                        f"更新日時: {updated_at_text}<br><br>"
                        f"リリースページ: <a href=\"{release_url}\">{release_url}</a><br><br>"
                        "インストーラをダウンロードして更新しますか？<br><br>"
                        "（ダウンロード後にアプリを終了し、インストーラを自動で起動します。完了後にアプリを再起動します）"
                    )

                    install_btn = box.addButton("インストール", QMessageBox.AcceptRole)
                    open_site_btn = box.addButton("更新サイトを開く", QMessageBox.ActionRole)
                    close_btn = box.addButton("閉じる", QMessageBox.RejectRole)
                    box.setDefaultButton(install_btn)

                    # 可能な環境ではURLクリックで外部ブラウザを開く
                    try:
                        label = box.findChild(QLabel, "qt_msgbox_label")
                        if label is not None:
                            label.setOpenExternalLinks(True)
                            label.setTextInteractionFlags(Qt.TextBrowserInteraction)
                    except Exception:
                        pass

                    box.exec()
                    if box.clickedButton() == open_site_btn:
                        try:
                            from classes.core.app_update_ui import open_url_in_browser

                            open_url_in_browser(release_url)
                        except Exception:
                            pass
                        return
                    if box.clickedButton() != install_btn:
                        return

                    self._download_and_install(url=url, version=latest_version, sha256=sha256)
                except Exception as e:
                    logger.error("更新確認UI処理でエラー: %s", e, exc_info=True)
                    _finish_ui(enable_button=True)
                    if not is_pytest:
                        QMessageBox.warning(self, "更新エラー", f"更新確認に失敗しました: {e}")

            def _invoke_check_update_now() -> None:
                if cancelled["v"]:
                    return
                try:
                    payload = app_updater_mod.check_update(REVISION)
                except Exception as exc:
                    payload = exc
                _handle_result(payload)

            class _UpdateCheckResultEmitter(QObject):
                @Slot(object)
                def _dispatch(self, payload: object) -> None:
                    _handle_result(payload)

            # この呼び出し中だけ使うEmitter（selfの子にして寿命を安定化）
            self._update_check_result_emitter = _UpdateCheckResultEmitter(self)

            # pytest 実行中はスレッドを避けて決定性/安定性を優先する
            if is_pytest:
                # singleShot(receiver, callable) は長いwidgetスイートで不安定になりうるので
                # 親付きQTimerで寿命を管理する
                try:
                    t = getattr(self, "_update_check_invoke_timer", None)
                    if t is not None:
                        t.stop()
                except Exception:
                    pass
                self._update_check_invoke_timer = QTimer(self)
                self._update_check_invoke_timer.setSingleShot(True)
                self._update_check_invoke_timer.timeout.connect(_invoke_check_update_now)
                self._update_check_invoke_timer.start(0)
                return

            # Qtのスレッド機構で更新確認を行い、UIをブロックしない
            thread = QThread()
            worker = _UpdateCheckWorker(app_updater_mod.check_update, REVISION)
            worker.moveToThread(thread)

            # キャンセル時のdisconnect用に参照を保持
            self._update_check_worker = worker
            self._update_check_thread = thread

            # 参照を保持（GC/親破棄で落ちると結果が届かない）
            _ACTIVE_UPDATE_CHECK_THREADS.add(thread)
            try:
                setattr(thread, "_update_check_worker", worker)
            except Exception:
                pass

            thread.started.connect(worker.run)
            self._update_check_dispatch_slot = self._update_check_result_emitter._dispatch
            worker.result_ready.connect(self._update_check_dispatch_slot, Qt.ConnectionType.QueuedConnection)
            worker.result_ready.connect(thread.quit)
            worker.result_ready.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            try:
                thread.finished.connect(lambda: _ACTIVE_UPDATE_CHECK_THREADS.discard(thread))
            except Exception:
                pass

            thread.start()

        except Exception as e:
            logger.error("更新確認/実行でエラー: %s", e, exc_info=True)
            if hasattr(self, "_update_check_btn"):
                self._update_check_btn.setEnabled(True)
            self._update_in_progress = False
            if not bool(os.environ.get("PYTEST_CURRENT_TEST")):
                QMessageBox.warning(self, "更新エラー", f"更新処理に失敗しました: {e}")

    def _download_and_install(self, *, url: str, version: str, sha256: str) -> None:
        """更新インストーラをDL→sha256検証→アプリ終了→インストーラ自動起動（進捗/キャンセル対応）。"""
        from classes.core.app_updater import (
            download,
            get_default_download_path,
            verify_sha256,
        )

        release_url = "https://github.com/MNagasako/misc-rde-tool-public/releases/latest"

        from classes.core.app_update_ui import UpdateDownloadDialog

        dst = get_default_download_path(version)

        if self._update_in_progress:
            return
        self._update_in_progress = True

        if hasattr(self, "_update_check_btn"):
            self._update_check_btn.setEnabled(False)

        dlg = UpdateDownloadDialog(title="更新", release_url=release_url, parent=self)
        dlg.setModal(True)
        dlg.set_status("ダウンロード準備中...")
        dlg.append_log(f"version={version}")
        dlg.append_log(f"dst={dst}")
        dlg.show()

        def progress_callback(current, total, message="処理中"):
            if dlg.is_cancelled():
                return False
            try:
                # bytes-based progress (preferred)
                dlg.progress_bytes_changed.emit(int(current or 0), int(total or 0), str(message))
            except Exception:
                pass
            return True

        def _finish_ui() -> None:
            try:
                dlg.close()
            except Exception:
                pass
            if hasattr(self, "_update_check_btn"):
                self._update_check_btn.setEnabled(True)
            self._update_in_progress = False

        def _end_in_progress_keep_dialog() -> None:
            """処理中フラグだけ解除し、ダイアログは残す（エラー内容を表示するため）。"""
            if hasattr(self, "_update_check_btn"):
                self._update_check_btn.setEnabled(True)
            self._update_in_progress = False

        def _prompt_and_start_update_on_ui_thread() -> None:
            try:
                # テスト中は更新（終了/インストーラ起動）を行わない
                if bool(os.environ.get("PYTEST_CURRENT_TEST")):
                    _finish_ui()
                    return

                from qt_compat.widgets import QMessageBox

                box = QMessageBox(self)
                box.setIcon(QMessageBox.Question)
                box.setWindowTitle("更新の準備ができました")
                box.setText("インストーラのダウンロードとsha256検証が完了しました。")
                box.setInformativeText(
                    "更新を開始するには、アプリを終了してからインストーラを起動する必要があります。\n\n"
                    "『更新を開始』を押すと、アプリを終了し、インストーラを自動で起動します。\n"
                    "インストール完了後にアプリを再起動します。"
                )

                start_btn = box.addButton("更新を開始", QMessageBox.AcceptRole)
                open_folder_btn = box.addButton("保存先を開く（手動）", QMessageBox.ActionRole)
                cancel_btn = box.addButton("キャンセル", QMessageBox.RejectRole)
                box.setDefaultButton(start_btn)
                box.exec()

                if box.clickedButton() == cancel_btn:
                    _finish_ui()
                    return

                if box.clickedButton() == open_folder_btn:
                    try:
                        if os.name == "nt":
                            import subprocess

                            subprocess.Popen(["explorer", "/select,", os.path.normpath(dst)], close_fds=True)
                    except Exception:
                        pass
                    QMessageBox.information(
                        self,
                        "保存先を開きました",
                        "セットアップを手動で実行する場合は、必ずアプリを終了してから実行してください。",
                    )
                    _finish_ui()
                    return

                # 更新開始（アプリ終了後にインストーラを起動し、完了後に再起動）
                try:
                    from classes.core.app_updater import run_installer_and_restart

                    # UIを閉じてから終了フローへ
                    try:
                        dlg.close()
                    except Exception:
                        pass

                    run_installer_and_restart(str(dst), wait_pid=int(os.getpid()))
                except Exception as e:
                    _finish_ui()
                    QMessageBox.warning(self, "更新エラー", f"インストーラ起動に失敗しました: {e}")
            except Exception as e:
                logger.error("更新後処理に失敗: %s", e, exc_info=True)
                _finish_ui()
                if not bool(os.environ.get("PYTEST_CURRENT_TEST")):
                    QMessageBox.warning(self, "更新エラー", f"更新後処理に失敗しました: {e}")

        def _worker_download() -> None:
            try:
                dlg.status_changed.emit("ダウンロード中...")

                def _log(line: str) -> None:
                    try:
                        dlg.log_line.emit(str(line))
                    except Exception:
                        pass

                download(url, dst, progress_callback=progress_callback, log_callback=_log, progress_mode="bytes")
                if dlg.is_cancelled():
                    QTimer.singleShot(0, self, _finish_ui)
                    return

                dlg.status_changed.emit("sha256検証中...")
                if not verify_sha256(dst, sha256):
                    def _bad_sha():
                        _finish_ui()
                        QMessageBox.warning(
                            self,
                            "更新失敗",
                            "sha256検証に失敗しました。\n安全のためインストーラは実行しません。",
                        )
                    QTimer.singleShot(0, self, _bad_sha)
                    return

                dlg.finish_success("ダウンロード完了")

                # アプリ終了/インストーラ起動を伴うためUIスレッドで処理する
                QTimer.singleShot(0, self, _prompt_and_start_update_on_ui_thread)
            except Exception as e:
                logger.error("更新ダウンロード/実行でエラー: %s", e, exc_info=True)
                def _on_err():
                    # workerスレッド→UIスレッドの呼び出しが環境によって不安定になり得るため、
                    # まずはダイアログ内に確実にエラーを表示する。
                    if dlg.is_cancelled():
                        _finish_ui()
                        return

                    extra = ""
                    try:
                        resp = getattr(e, "response", None)
                        status = getattr(resp, "status_code", None)
                        if int(status or 0) == 404 and "github.com" in str(url):
                            extra = (
                                "\n\nURLが見つかりません（404）でした。\n"
                                "GitHub Releases にインストーラexeが添付されていないか、ファイル名/タグが一致していない可能性があります。\n\n"
                                "対処: GitHubのリリースページで Assets を確認してください。\n"
                                f"  期待ファイル名: arim_rde_tool_setup.{version}.exe\n"
                            )
                    except Exception:
                        extra = ""

                    try:
                        dlg.append_log(f"ERROR: {e}{extra}")
                    except Exception:
                        pass
                    try:
                        dlg.finish_error("更新ダウンロードに失敗しました（詳細はログを参照）")
                    except Exception:
                        pass

                    # エラー表示のためダイアログは残し、ボタン等は復帰
                    _end_in_progress_keep_dialog()
                QTimer.singleShot(0, self, _on_err)

        threading.Thread(target=_worker_download, daemon=True).start()

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

        self.update_check_checkbox = QCheckBox("起動時に更新を確認する（既定: 確認する）")
        self.update_check_checkbox.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: normal;"
        )
        layout.addWidget(self.update_check_checkbox)

        self.update_prompt_checkbox = QCheckBox("起動時の更新確認ダイアログを表示する（既定: 表示）")
        self.update_prompt_checkbox.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: normal;"
        )
        layout.addWidget(self.update_prompt_checkbox)

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
            cfg = get_config_manager()
            enabled = bool(cfg.get("app.enable_splash_screen", True))
            self.splash_checkbox.setChecked(enabled)

            update_enabled = bool(cfg.get("app.update.auto_check_enabled", True))
            self.update_check_checkbox.setChecked(update_enabled)

            prompt_enabled = bool(cfg.get("app.update.startup_prompt_enabled", True))
            self.update_prompt_checkbox.setChecked(prompt_enabled)
        except Exception as e:
            logger.debug("スプラッシュ設定の読み込みに失敗: %s", e)
            try:
                self.splash_checkbox.setChecked(True)
                self.update_check_checkbox.setChecked(True)
                self.update_prompt_checkbox.setChecked(True)
            except Exception:
                pass

    def save_startup_settings(self):
        """起動関連設定の保存"""
        try:
            cfg = get_config_manager()
            cfg.set("app.enable_splash_screen", bool(self.splash_checkbox.isChecked()))
            cfg.set("app.update.auto_check_enabled", bool(self.update_check_checkbox.isChecked()))
            cfg.set("app.update.startup_prompt_enabled", bool(self.update_prompt_checkbox.isChecked()))
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
