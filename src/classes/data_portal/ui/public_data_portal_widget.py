"""Public (no-login) ARIM Data Portal widget.

This widget is intended for the Settings dialog/tab and must not affect the
existing authenticated DataPortalWidget.

Tabs:
- Fetch: POST keyword search against nanonet.go.jp/data_service/arim_data.php
- Listing: Show latest exported search results
"""

from __future__ import annotations

import logging

from qt_compat.widgets import QTabWidget, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


class PublicDataPortalWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

        from classes.theme import ThemeManager

        ThemeManager.instance().theme_changed.connect(self.refresh_theme)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        self._setup_tabs()

    def _setup_tabs(self) -> None:
        try:
            from classes.data_portal.ui.public_fetch_tab import PublicDataPortalFetchTab
            from classes.data_portal.ui.public_listing_tab import PublicDataPortalListingTab

            self.fetch_tab = PublicDataPortalFetchTab(self)
            self.tab_widget.addTab(self.fetch_tab, "📊 データ取得")

            self.listing_tab = PublicDataPortalListingTab(self)
            self.tab_widget.addTab(self.listing_tab, "📋 一覧表示")

            self.tab_widget.currentChanged.connect(self._on_tab_changed)

        except Exception as exc:
            logger.error("PublicDataPortalWidget: タブ初期化エラー: %s", exc, exc_info=True)
            from qt_compat.widgets import QLabel

            error_label = QLabel(f"⚠️ 公開データポータルタブの初期化に失敗しました\n{exc}")
            error_label.setWordWrap(True)
            self.tab_widget.addTab(error_label, "⚠ エラー")

    def _on_tab_changed(self, index: int) -> None:
        tab = self.tab_widget.widget(index)

        # 取得タブの環境選択に合わせて一覧表示タブの参照先フォルダを切り替える
        try:
            fetch_tab = getattr(self, "fetch_tab", None)
            listing_tab = getattr(self, "listing_tab", None)
            env = None
            if fetch_tab is not None and hasattr(fetch_tab, "env_combo"):
                env = fetch_tab.env_combo.currentData()
            if listing_tab is not None:
                set_env = getattr(listing_tab, "set_environment", None)
                if callable(set_env):
                    set_env(str(env or "production"))
        except Exception:
            pass

        refresh = getattr(tab, "refresh_from_disk", None)
        if callable(refresh):
            refresh()

    def refresh_theme(self) -> None:
        try:
            for tab in (getattr(self, "fetch_tab", None), getattr(self, "listing_tab", None)):
                refresh = getattr(tab, "refresh_theme", None)
                if callable(refresh):
                    refresh()
            self.update()
        except Exception as exc:
            logger.error("PublicDataPortalWidget: テーマ更新エラー: %s", exc)
