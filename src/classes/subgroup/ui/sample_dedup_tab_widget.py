"""Sample dedup tab widget."""

from __future__ import annotations

from qt_compat.core import QTimer
from qt_compat.widgets import QApplication, QLabel, QSizePolicy, QTabWidget, QVBoxLayout, QWidget

from classes.subgroup.ui.sample_dedup_listing_widget import SampleDedupListingWidget
from classes.subgroup.util.sample_dedup_table_records import build_sample_listing2_rows_from_files, get_default_columns_list2
from classes.utils.ui_responsiveness import schedule_deferred_ui_task


class SampleDedupTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
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

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            schedule_deferred_ui_task(self.tab_widget, "sample-dedup-listing2-tab", self._ensure_listing2_built)

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
