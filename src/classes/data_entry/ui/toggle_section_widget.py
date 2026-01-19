"""Toggle-able section widget for Data Entry UI.

Provides a small header with a title and a toggle button that switches
between a read-only summary view and an editable form view.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from qt_compat.core import Qt
from qt_compat.widgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color


@dataclass(frozen=True)
class ToggleSectionTexts:
    show_edit: str = "✎ 入力"
    show_summary: str = "☰ 表示"


class ToggleSectionWidget(QWidget):
    """A section widget that can toggle between summary and edit widgets."""

    def __init__(
        self,
        title: str,
        parent: Optional[QWidget] = None,
        *,
        default_mode: str = "summary",
        texts: ToggleSectionTexts | None = None,
    ) -> None:
        super().__init__(parent)

        self._texts = texts or ToggleSectionTexts()
        self._summary_widget: Optional[QWidget] = None
        self._edit_widget: Optional[QWidget] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self._title_label = QLabel(title, header)
        self._title_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._title_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: bold;"
        )

        self._toggle_button = QPushButton(header)
        self._toggle_button.setObjectName("toggleButton")
        self._toggle_button.setCheckable(True)
        self._toggle_button.clicked.connect(self._on_toggle_clicked)
        self._toggle_button.setStyleSheet(self._build_toggle_button_style())

        header_layout.addWidget(self._title_label, 1)
        header_layout.addWidget(self._toggle_button, 0, Qt.AlignRight)
        root.addWidget(header)

        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        root.addWidget(self._body)

        self.set_mode(default_mode)

    def set_summary_widget(self, widget: QWidget) -> None:
        if self._summary_widget is not None:
            self._body_layout.removeWidget(self._summary_widget)
            self._summary_widget.setParent(None)

        self._summary_widget = widget
        self._body_layout.addWidget(widget)
        self._apply_visibility()

    def set_edit_widget(self, widget: QWidget) -> None:
        if self._edit_widget is not None:
            self._body_layout.removeWidget(self._edit_widget)
            self._edit_widget.setParent(None)

        self._edit_widget = widget
        self._body_layout.addWidget(widget)
        self._apply_visibility()

    def mode(self) -> str:
        return "edit" if self._toggle_button.isChecked() else "summary"

    def set_mode(self, mode: str) -> None:
        normalized = (mode or "").strip().lower()
        checked = normalized in {"edit", "input", "form"}
        self._toggle_button.setChecked(checked)
        self._apply_visibility()

    def _apply_visibility(self) -> None:
        edit_mode = self._toggle_button.isChecked()
        self._toggle_button.setText(self._texts.show_summary if edit_mode else self._texts.show_edit)

        if self._summary_widget is not None:
            self._summary_widget.setVisible(not edit_mode)
        if self._edit_widget is not None:
            self._edit_widget.setVisible(edit_mode)

        # Allow summary widgets to refresh themselves when they become visible.
        if not edit_mode and self._summary_widget is not None:
            refresh = getattr(self._summary_widget, "refresh", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception:
                    pass

    def _on_toggle_clicked(self) -> None:
        self._apply_visibility()

    @staticmethod
    def _build_toggle_button_style() -> str:
        return (
            "QPushButton#toggleButton {"
            f"  background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND)};"
            f"  color: {get_color(ThemeKey.BUTTON_NEUTRAL_TEXT)};"
            f"  border: 1px solid {get_color(ThemeKey.BUTTON_NEUTRAL_BORDER)};"
            "  border-radius: 6px;"
            "  padding: 2px 10px;"
            "  min-height: 24px;"
            "}"
            "QPushButton#toggleButton:hover {"
            f"  background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER)};"
            "}"
            "QPushButton#toggleButton:checked {"
            f"  background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};"
            f"  color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};"
            f"  border: 1px solid {get_color(ThemeKey.BUTTON_INFO_BORDER)};"
            "}"
            "QPushButton#toggleButton:checked:hover {"
            f"  background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};"
            "}"
        )
