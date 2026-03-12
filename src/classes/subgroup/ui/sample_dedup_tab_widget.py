"""Sample dedup tab widget."""

from __future__ import annotations

from qt_compat.core import QTimer
from qt_compat.widgets import QApplication, QLabel, QSizePolicy, QTabWidget, QVBoxLayout, QWidget

from classes.subgroup.ui.sample_dedup_listing_widget import SampleDedupListingWidget
from classes.subgroup.util.sample_dedup_table_records import build_sample_listing2_rows_from_files, get_default_columns_list2
from classes.utils.window_sizing import is_window_maximized, resize_main_window


class SampleDedupTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # key: tab index, value: QSize
        self._tab_window_sizes: dict[int, object] = {}
        self._current_tab_index: int | None = None
        self._last_tab_index_applied: int | None = None
        self._listing2_widget = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tab_widget = QTabWidget(self)

        listing_tab = SampleDedupListingWidget(self.tab_widget)
        self.tab_widget.addTab(listing_tab, "一覧")

        listing2_placeholder = QWidget(self.tab_widget)
        placeholder_layout = QVBoxLayout(listing2_placeholder)
        placeholder_layout.setContentsMargins(12, 12, 12, 12)
        placeholder_layout.addWidget(QLabel(QApplication.translate('SampleDedupTabWidget', '一覧２タブを読み込み中...')))
        placeholder_layout.addStretch(1)
        self.tab_widget.addTab(listing2_placeholder, '一覧２')

        layout.addWidget(self.tab_widget)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def showEvent(self, event):  # type: ignore[override]
        super().showEvent(event)
        try:
            QTimer.singleShot(0, lambda: self._on_tab_changed(self.tab_widget.currentIndex()))
        except Exception:
            pass

    def event(self, event):  # type: ignore[override]
        try:
            if event.type() == event.Type.WindowActivate:
                QTimer.singleShot(0, lambda: self._on_tab_changed(self.tab_widget.currentIndex()))
        except Exception:
            pass
        return super().event(event)

    def _target_size_90pct(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return None
        try:
            geo = screen.availableGeometry()
        except Exception:
            geo = screen.geometry()
        w = max(640, int(geo.width() * 0.9))
        h = max(480, int(geo.height() * 0.9))
        return w, h

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self._ensure_listing2_built()

        top_level = self.window()

        # Save previous tab size.
        try:
            if (
                self._current_tab_index is not None
                and top_level
                and not is_window_maximized(top_level)
                and top_level.size().isValid()
            ):
                self._tab_window_sizes[self._current_tab_index] = top_level.size()
        except Exception:
            pass

        self._current_tab_index = index

        if top_level and is_window_maximized(top_level):
            self._last_tab_index_applied = index
            return

        # Avoid re-applying resize for the same tab unless we actually switch tabs.
        if self._last_tab_index_applied == index:
            return

        if not top_level:
            return

        # Restore saved size for this tab.
        try:
            saved = self._tab_window_sizes.get(index)
            if saved is not None and getattr(saved, "isValid", lambda: False)():
                resize_main_window(top_level, saved.width(), saved.height())
                self._last_tab_index_applied = index
                return
        except Exception:
            pass

        # First time for this tab: apply 90% screen size.
        target = self._target_size_90pct()
        if target:
            try:
                resize_main_window(top_level, target[0], target[1])
            except Exception:
                pass
            try:
                self._tab_window_sizes[index] = top_level.size()
            except Exception:
                pass
        self._last_tab_index_applied = index

    def _ensure_listing2_built(self) -> None:
        if self._listing2_widget is not None:
            return

        listing2_tab = SampleDedupListingWidget(
            self.tab_widget,
            title='🧪 試料一覧２',
            columns_provider=get_default_columns_list2,
            rows_builder=build_sample_listing2_rows_from_files,
            cache_enabled=False,
            multiline_link_column_key='tile_dataset_grant',
        )
        self._listing2_widget = listing2_tab
        try:
            self.tab_widget.blockSignals(True)
            self.tab_widget.removeTab(1)
            self.tab_widget.insertTab(1, listing2_tab, '一覧２')
            self.tab_widget.setCurrentIndex(1)
        finally:
            try:
                self.tab_widget.blockSignals(False)
            except Exception:
                pass


def create_sample_dedup_tab_widget(parent=None):
    return SampleDedupTabWidget(parent)
