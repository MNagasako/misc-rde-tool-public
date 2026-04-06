"""
データポータルメインウィジェット

ログイン設定タブとデータセットアップロードタブを統合したタブウィジェット
"""

from typing import Optional, TYPE_CHECKING

from qt_compat import QtGui, QtWidgets
from qt_compat.widgets import (
    QApplication, QWidget, QVBoxLayout, QTabWidget, QLabel
)
from qt_compat.core import Signal, QTimer

from classes.managers.log_manager import get_logger
from classes.theme import ThemeKey, get_color
from classes.utils.ui_responsiveness import schedule_deferred_ui_task, start_ui_responsiveness_run
from .login_settings_tab import LoginSettingsTab
if TYPE_CHECKING:
    from .master_data_tab import MasterDataTab
    from .dataset_upload_tab import DatasetUploadTab

logger = get_logger("DataPortal.Widget")


class DataPortalWidget(QWidget):
    """
    データポータルメインウィジェット
    
    タブ構成:
    1. ログイン設定タブ - 認証情報管理
    2. マスタタブ - マスタデータ管理
    3. データセットタブ - JSONアップロード
    4. 一括タブ - 一覧から一括操作
    5. 一覧タブ - 公開/管理CSV統合表示
    """
    
    # シグナル定義
    login_test_completed = Signal(bool, str)  # ログインテスト完了
    upload_completed = Signal(bool, str)  # アップロード完了
    master_fetched = Signal(str, bool)  # マスタ取得完了
    
    def __init__(self, parent=None):
        """初期化"""
        super().__init__(parent)
        self.setObjectName("dataPortalWidgetRoot")

        # 遅延生成用
        self.master_data_tab: Optional["MasterDataTab"] = None
        self._master_placeholder = None
        self._pending_portal_client = None
        self._pending_environment: str = "production"

        self.dataset_upload_tab: Optional["DatasetUploadTab"] = None
        self._upload_placeholder = None

        # 一括タブ（初回表示時まで生成を遅延）
        self.bulk_tab = None
        self._bulk_placeholder = None

        # 一覧タブ（公開cache + 管理CSV）
        self.listing_tab = None
        self._listing_placeholder = None

        self._current_tab_index: int | None = None
        self._last_theme_refresh_mode: str | None = None
        self._replacing_tab = False

        self._init_ui()
        self._connect_signals()
        try:
            self._current_tab_index = self.tab_widget.currentIndex()
        except Exception:
            self._current_tab_index = 0
        
        # テーマ変更シグナルに接続
        from classes.theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        
        logger.info("データポータルウィジェット初期化完了")

    def _build_base_stylesheet(self) -> str:
        return f"""
            QWidget#dataPortalWidgetRoot {{
                background-color: {get_color(ThemeKey.WINDOW_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
            }}
            QWidget#dataPortalWidgetRoot QLabel {{
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
            }}
            QWidget#dataPortalWidgetRoot QGroupBox {{
                background-color: {get_color(ThemeKey.GROUPBOX_BACKGROUND)};
                border: 1px solid {get_color(ThemeKey.GROUPBOX_BORDER)};
                border-radius: 5px;
                margin-top: 6px;
                padding-top: 10px;
            }}
            QWidget#dataPortalWidgetRoot QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                padding: 0 4px;
                background-color: {get_color(ThemeKey.GROUPBOX_BACKGROUND)};
                color: {get_color(ThemeKey.GROUPBOX_TITLE_TEXT)};
                font-weight: bold;
            }}
            QWidget#dataPortalWidgetRoot QLineEdit,
            QWidget#dataPortalWidgetRoot QPlainTextEdit,
            QWidget#dataPortalWidgetRoot QTextEdit {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                border: {get_color(ThemeKey.INPUT_BORDER_WIDTH)} solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 4px;
                padding: 4px;
            }}
            QWidget#dataPortalWidgetRoot QComboBox {{
                background-color: {get_color(ThemeKey.COMBO_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: 1px solid {get_color(ThemeKey.COMBO_BORDER)};
                border-radius: 4px;
                padding: 2px 6px;
            }}
            QWidget#dataPortalWidgetRoot QComboBox::drop-down {{
                width: 18px;
                background-color: {get_color(ThemeKey.COMBO_ARROW_BACKGROUND)};
                border-left: 1px solid {get_color(ThemeKey.COMBO_BORDER)};
            }}
            QWidget#dataPortalWidgetRoot QCheckBox,
            QWidget#dataPortalWidgetRoot QRadioButton {{
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
            }}
            QWidget#dataPortalWidgetRoot QTabWidget::pane {{
                border: 1px solid {get_color(ThemeKey.TAB_BORDER)};
                background: {get_color(ThemeKey.TAB_BACKGROUND)};
                border-radius: 4px;
            }}
            QWidget#dataPortalWidgetRoot QTabBar::tab {{
                background: {get_color(ThemeKey.TAB_INACTIVE_BACKGROUND)};
                color: {get_color(ThemeKey.TAB_INACTIVE_TEXT)};
                padding: 6px 12px;
                border: 1px solid {get_color(ThemeKey.TAB_BORDER)};
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }}
            QWidget#dataPortalWidgetRoot QTabBar::tab:selected {{
                background: {get_color(ThemeKey.TAB_ACTIVE_BACKGROUND)};
                color: {get_color(ThemeKey.TAB_ACTIVE_TEXT)};
                border: 1px solid {get_color(ThemeKey.TAB_ACTIVE_BORDER)};
            }}
            QWidget#dataPortalWidgetRoot QTabBar::tab:hover {{
                background: {get_color(ThemeKey.TABLE_ROW_BACKGROUND_HOVER)};
            }}
        """
    
    def _init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # タブウィジェット作成
        self.tab_widget = QTabWidget()
        
        # ログイン設定タブ
        self.login_settings_tab = LoginSettingsTab(self)
        self.tab_widget.addTab(self.login_settings_tab, "🔐 ログイン設定")

        # マスタデータタブ（初回表示時まで生成を遅延）
        self._master_placeholder = QWidget(self)
        placeholder_layout = QVBoxLayout(self._master_placeholder)
        placeholder_layout.setContentsMargins(12, 12, 12, 12)
        placeholder_layout.addWidget(QLabel("読み込み中..."))
        placeholder_layout.addStretch()
        self.tab_widget.addTab(self._master_placeholder, "📋 マスタ")

        # データセットJSONアップロードタブ（初回表示時まで生成を遅延）
        self._upload_placeholder = QWidget(self)
        upload_placeholder_layout = QVBoxLayout(self._upload_placeholder)
        upload_placeholder_layout.setContentsMargins(12, 12, 12, 12)
        upload_placeholder_layout.addWidget(QLabel("読み込み中..."))
        upload_placeholder_layout.addStretch()
        self.tab_widget.addTab(self._upload_placeholder, "📤 データカタログ")

        # 一括タブ（初回表示時まで生成を遅延）
        self._bulk_placeholder = QWidget(self)
        bulk_placeholder_layout = QVBoxLayout(self._bulk_placeholder)
        bulk_placeholder_layout.setContentsMargins(12, 12, 12, 12)
        bulk_placeholder_layout.addWidget(QLabel("読み込み中..."))
        bulk_placeholder_layout.addStretch()
        self.tab_widget.addTab(self._bulk_placeholder, "📦 一括")

        # 一覧タブ（初回表示時まで生成を遅延）
        self._listing_placeholder = QWidget(self)
        listing_placeholder_layout = QVBoxLayout(self._listing_placeholder)
        listing_placeholder_layout.setContentsMargins(12, 12, 12, 12)
        listing_placeholder_layout.addWidget(QLabel("読み込み中..."))
        listing_placeholder_layout.addStretch()
        self.tab_widget.addTab(self._listing_placeholder, "📋 一覧")
        
        layout.addWidget(self.tab_widget)
        self.setStyleSheet(self._build_base_stylesheet())

        # タブ切替で遅延生成
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
    
    def _connect_signals(self):
        """シグナル接続"""
        # ログインテスト完了シグナルを転送
        self.login_settings_tab.login_test_completed.connect(
            self._on_login_test_completed
        )
        
        # アップロードタブは遅延生成のため、生成時に接続する
        
        # マスタタブは遅延生成のため、生成時に接続する
        
        # 認証情報保存後にアップロードタブを有効化
        self.login_settings_tab.credentials_saved.connect(
            self._on_credentials_saved
        )

        # 環境切替に一覧タブを追従
        try:
            combo = getattr(self.login_settings_tab, "env_combo", None)
            if combo is not None and hasattr(combo, "currentIndexChanged"):
                combo.currentIndexChanged.connect(self._on_environment_combo_changed)
        except Exception:
            pass

    def _on_environment_combo_changed(self, _index: int) -> None:
        try:
            env = self.login_settings_tab.env_combo.currentData()  # type: ignore[attr-defined]
        except Exception:
            env = None
        env = str(env or "production").strip() or "production"
        self._pending_environment = env

        if self.listing_tab is not None:
            try:
                set_env = getattr(self.listing_tab, "set_environment", None)
                if callable(set_env):
                    set_env(env)
            except Exception as e:
                logger.error("一覧タブへの環境反映に失敗: %s", e)
    
    def _on_login_test_completed(self, success: bool, message: str):
        """ログインテスト完了時の処理"""
        # シグナルを転送
        self.login_test_completed.emit(success, message)
        
        # 成功時にPortalClientをマスタタブに設定（マスタタブが未生成なら保留）
        if success and hasattr(self.login_settings_tab, 'portal_client'):
            portal_client = self.login_settings_tab.portal_client
            if portal_client:
                self._pending_portal_client = portal_client
                if self.master_data_tab is not None:
                    self.master_data_tab.set_portal_client(portal_client)
                    logger.info("マスタタブにPortalClientを設定しました")
                if self.listing_tab is not None:
                    try:
                        set_client = getattr(self.listing_tab, "set_portal_client", None)
                        if callable(set_client):
                            set_client(portal_client)
                    except Exception as e:
                        logger.error("一覧タブにPortalClientを設定できません: %s", e)

    def _on_tab_changed(self, index: int) -> None:
        """タブ切替時の遅延初期化"""
        try:
            if self._replacing_tab:
                self._current_tab_index = index
                return

            # 0: login, 1: master, 2: upload, 3: bulk, 4: listing
            if index == 0:
                try:
                    if hasattr(self, "login_settings_tab") and hasattr(self.login_settings_tab, "auto_test_connections"):
                        self.login_settings_tab.auto_test_connections()
                except Exception:
                    pass
            elif index == 1:
                run = start_ui_responsiveness_run("data_portal", "master_tab", "lazy_tab_build", tab_index=index, cache_state="miss")
                run.mark("placeholder_visible")
                schedule_deferred_ui_task(self.tab_widget, "data-portal-master-tab", lambda session=run: self._ensure_master_tab(session))
            elif index == 2:
                run = start_ui_responsiveness_run("data_portal", "upload_tab", "lazy_tab_build", tab_index=index, cache_state="miss")
                run.mark("placeholder_visible")
                schedule_deferred_ui_task(self.tab_widget, "data-portal-upload-tab", lambda session=run: self._ensure_upload_tab(run=session))
            elif index == 3:
                run = start_ui_responsiveness_run("data_portal", "bulk_tab", "lazy_tab_build", tab_index=index, cache_state="miss")
                run.mark("placeholder_visible")
                schedule_deferred_ui_task(self.tab_widget, "data-portal-bulk-tab", lambda session=run: self._ensure_bulk_tab(session))
            elif index == 4:
                run = start_ui_responsiveness_run("data_portal", "listing_tab", "lazy_tab_build", tab_index=index, cache_state="miss")
                run.mark("placeholder_visible")
                schedule_deferred_ui_task(self.tab_widget, "data-portal-listing-tab", lambda session=run: self._ensure_listing_tab(session))

            self._current_tab_index = index
            try:
                QTimer.singleShot(0, lambda idx=index: self._finalize_tab_change(idx))
            except Exception:
                self._finalize_tab_change(index)
        except Exception as e:
            logger.error("DataPortalWidget: tab change handling failed: %s", e)

    def _replace_lazy_tab(self, idx: int, widget: QWidget, title: str, *, set_current: bool = True) -> None:
        """placeholder を実タブへ差し替える間の currentChanged 再入を防ぐ。"""
        self._replacing_tab = True
        try:
            self.tab_widget.blockSignals(True)
            self.tab_widget.removeTab(idx)
            self.tab_widget.insertTab(idx, widget, title)
            if set_current:
                self.tab_widget.setCurrentIndex(idx)
        finally:
            self.tab_widget.blockSignals(False)
            self._replacing_tab = False

    def _finalize_tab_change(self, index: int) -> None:
        self._refresh_tab_theme(index)

    def _ensure_master_tab(self, run=None) -> None:
        if self.master_data_tab is not None:
            if run is not None:
                run.finish(success=True, cache_state="memory_hit")
            return
        idx = self.tab_widget.indexOf(self._master_placeholder)
        if idx < 0:
            # 何らかの理由で placeholder が無い場合は末尾に追加
            idx = 1

        from .master_data_tab import MasterDataTab

        if run is not None:
            run.mark("build_start")
        self.master_data_tab = MasterDataTab(self)
        # シグナルを転送
        self.master_data_tab.master_fetched.connect(self.master_fetched.emit)
        # 保留していた PortalClient を設定
        if self._pending_portal_client is not None:
            try:
                self.master_data_tab.set_portal_client(self._pending_portal_client)
                logger.info("マスタタブにPortalClientを設定しました")
            except Exception as e:
                logger.error("マスタタブへのPortalClient設定に失敗: %s", e)

        # 置換
        self._replace_lazy_tab(idx, self.master_data_tab, "📋 マスタ")
        if run is not None:
            run.interactive(widget_class=type(self.master_data_tab).__name__)
            run.complete(widget_class=type(self.master_data_tab).__name__)
            run.finish(success=True)

    def _ensure_upload_tab(self, *, set_current: bool = True, run=None) -> None:
        if self.dataset_upload_tab is not None:
            if run is not None:
                run.finish(success=True, cache_state="memory_hit")
            return
        idx = self.tab_widget.indexOf(self._upload_placeholder)
        if idx < 0:
            idx = 2

        from .dataset_upload_tab import DatasetUploadTab

        if run is not None:
            run.mark("build_start")
        self.dataset_upload_tab = DatasetUploadTab(self)
        # シグナルを転送
        self.dataset_upload_tab.upload_completed.connect(self.upload_completed.emit)

        # 置換
        self._replace_lazy_tab(idx, self.dataset_upload_tab, "📤 データカタログ", set_current=set_current)
        if run is not None:
            run.interactive(widget_class=type(self.dataset_upload_tab).__name__)
            run.complete(widget_class=type(self.dataset_upload_tab).__name__)
            run.finish(success=True)

    def _ensure_bulk_tab(self, run=None) -> None:
        if self.bulk_tab is not None:
            if run is not None:
                run.finish(success=True, cache_state="memory_hit")
            return
        idx = self.tab_widget.indexOf(self._bulk_placeholder)
        if idx < 0:
            idx = 3

        from .portal_bulk_tab import DataPortalBulkTab

        if run is not None:
            run.mark("build_start")
        self.bulk_tab = DataPortalBulkTab(self)

        self._replace_lazy_tab(idx, self.bulk_tab, "📦 一括")
        if run is not None:
            run.interactive(widget_class=type(self.bulk_tab).__name__)
            run.complete(widget_class=type(self.bulk_tab).__name__)
            run.finish(success=True)

    def _ensure_listing_tab(self, run=None) -> None:
        if self.listing_tab is not None:
            if run is not None:
                run.finish(success=True, cache_state="memory_hit")
            return
        idx = self.tab_widget.indexOf(self._listing_placeholder)
        if idx < 0:
            idx = 4

        from .portal_listing_tab import PortalListingTab

        if run is not None:
            run.mark("build_start")
        self.listing_tab = PortalListingTab(self)

        # 現在の環境を反映
        try:
            env = self.login_settings_tab.env_combo.currentData()
        except Exception:
            env = self._pending_environment
        env = str(env or "production").strip() or "production"
        self._pending_environment = env
        try:
            set_env = getattr(self.listing_tab, "set_environment", None)
            if callable(set_env):
                set_env(env)
        except Exception:
            pass

        # 保留していた PortalClient を設定
        if self._pending_portal_client is not None:
            try:
                set_client = getattr(self.listing_tab, "set_portal_client", None)
                if callable(set_client):
                    set_client(self._pending_portal_client)
            except Exception as e:
                logger.error("一覧タブへのPortalClient設定に失敗: %s", e)
        else:
            # 保存済み認証情報があるなら、接続テスト無しで PortalClient を生成して渡す
            try:
                creator = getattr(self.login_settings_tab, "create_portal_client_for_environment", None)
                portal_client = creator(env) if callable(creator) else None
                if portal_client is not None:
                    self._pending_portal_client = portal_client
                    set_client = getattr(self.listing_tab, "set_portal_client", None)
                    if callable(set_client):
                        set_client(portal_client)
            except Exception:
                pass

        # 置換
        self._replace_lazy_tab(idx, self.listing_tab, "📋 一覧")
        if run is not None:
            run.interactive(widget_class=type(self.listing_tab).__name__)
            run.complete(widget_class=type(self.listing_tab).__name__)
            run.finish(success=True)
    
    def _on_credentials_saved(self, environment: str):
        """認証情報保存後の処理"""
        logger.info(f"認証情報保存完了: {environment}")
        # 接続テストを実施していない場合でも、保存直後から各タブでAPIを利用できるよう
        # PortalClient を生成して共有する（実際のログインは各処理で必要になった時点で行う）。
        try:
            creator = getattr(self.login_settings_tab, "create_portal_client_for_environment", None)
            portal_client = creator(environment) if callable(creator) else None
        except Exception as e:
            logger.error("PortalClient生成に失敗: %s", e)
            portal_client = None

        if portal_client is None:
            return

        self._pending_portal_client = portal_client

        if self.master_data_tab is not None:
            try:
                self.master_data_tab.set_portal_client(portal_client)
            except Exception as e:
                logger.error("マスタタブへのPortalClient設定に失敗: %s", e)

        if self.listing_tab is not None:
            try:
                set_client = getattr(self.listing_tab, "set_portal_client", None)
                if callable(set_client):
                    set_client(portal_client)
            except Exception as e:
                logger.error("一覧タブへのPortalClient設定に失敗: %s", e)

    def _get_tab_widget_for_index(self, index: int):
        if index == 0:
            return getattr(self, "login_settings_tab", None)
        if index == 1:
            return getattr(self, "master_data_tab", None)
        if index == 2:
            return getattr(self, "dataset_upload_tab", None)
        if index == 3:
            return getattr(self, "bulk_tab", None)
        if index == 4:
            return getattr(self, "listing_tab", None)
        return None

    def _refresh_tab_theme(self, index: int) -> None:
        child = self._get_tab_widget_for_index(index)
        if child is not None and hasattr(child, 'refresh_theme'):
            child.refresh_theme()

    @staticmethod
    def _repolish_widget(widget: QWidget) -> None:
        try:
            style = widget.style()
            if style is not None:
                style.unpolish(widget)
                style.polish(widget)
        except Exception:
            pass

        try:
            if isinstance(widget, QtWidgets.QAbstractScrollArea):
                viewport = widget.viewport()
                if viewport is not None:
                    style = viewport.style()
                    if style is not None:
                        style.unpolish(viewport)
                        style.polish(viewport)
                    viewport.update()
        except Exception:
            pass

        try:
            widget.update()
        except Exception:
            pass

    def _refresh_hover_styles_for_widget(self, hovered_widget: Optional[QWidget] = None) -> None:
        try:
            hovered = hovered_widget
            if hovered is None:
                hovered = QApplication.widgetAt(QtGui.QCursor.pos())
            if hovered is None:
                return
            if hovered is not self and not self.isAncestorOf(hovered):
                return

            chain: list[QWidget] = []
            current = hovered
            while current is not None:
                chain.append(current)
                if current is self:
                    break
                current = current.parentWidget()

            for widget in reversed(chain):
                self._repolish_widget(widget)

            if hovered is not self:
                self._repolish_widget(hovered)
        except Exception:
            pass
    
    def refresh_theme(self):
        """テーマ変更時のスタイル更新"""
        try:
            try:
                from classes.theme import ThemeManager

                current_mode = ThemeManager.instance().get_mode().value
            except Exception:
                current_mode = None

            if current_mode is not None and self._last_theme_refresh_mode == current_mode:
                return

            self.setStyleSheet(self._build_base_stylesheet())

            current_index = self.tab_widget.currentIndex() if hasattr(self, "tab_widget") else 0
            self._refresh_tab_theme(current_index)
            self._refresh_hover_styles_for_widget()

            if current_mode is not None:
                self._last_theme_refresh_mode = current_mode
            
            # ウィジェット全体を再描画
            self.update()
            logger.debug("DataPortalWidget: テーマ更新完了")
        except Exception as e:
            logger.error(f"DataPortalWidget: テーマ更新エラー: {e}")
    
    def switch_to_login_tab(self):
        """ログイン設定タブに切り替え"""
        self.tab_widget.setCurrentIndex(0)
    
    def switch_to_master_tab(self):
        """マスタタブに切り替え"""
        self.tab_widget.setCurrentIndex(1)
    
    def switch_to_upload_tab(self):
        """データセットタブに切り替え"""
        self.tab_widget.setCurrentIndex(2)

    def switch_to_bulk_tab(self):
        """一括タブに切り替え"""
        self.tab_widget.setCurrentIndex(3)

    def switch_to_listing_tab(self):
        """一覧タブに切り替え"""
        self.tab_widget.setCurrentIndex(4)

    def open_upload_and_select_dataset(self, dataset_id: str) -> bool:
        """データカタログ(アップロード)タブを開き、dataset_idを選択する。

        DataPortalWidget は upload タブを遅延生成するため、本メソッドで
        生成→タブ移動→選択までを一括で行う。
        """

        self.switch_to_upload_tab()
        try:
            self._ensure_upload_tab()
        except Exception as e:
            logger.error("DataPortalWidget: failed to ensure upload tab: %s", e)
            return False

        try:
            if self.dataset_upload_tab is None:
                return False
            select_fn = getattr(self.dataset_upload_tab, "select_dataset_id", None)
            if callable(select_fn):
                return bool(select_fn(dataset_id))
        except Exception as e:
            logger.error("DataPortalWidget: dataset selection failed: %s", e)
        return False
