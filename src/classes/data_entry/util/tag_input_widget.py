from __future__ import annotations

import logging

from typing import List

from qt_compat.core import Qt, Signal
from qt_compat.widgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color

logger = logging.getLogger(__name__)


class TagInputWidget(QFrame):
    """タグ入力（カンマ区切り）をチップ表示するウィジェット。

    - 表示: 既に確定したタグをボタン的(チップ)に表示
    - 入力: 内部の QLineEdit に入力し、`,` / Enter / Tab で確定
    - 互換: 既存実装が期待する `.text()` / `.setText()` / `.setPlaceholderText()` を提供

    NOTE: API に渡す値は従来どおりカンマ区切り文字列。
    """

    textChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._tags: List[str] = []
        self._placeholder_text = ""

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(6, 2, 6, 2)
        self._layout.setSpacing(4)

        self._chips_container = QWidget(self)
        self._chips_layout = QHBoxLayout(self._chips_container)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(4)
        self._layout.addWidget(self._chips_container, 0)

        self._line_edit = QLineEdit(self)
        self._line_edit.setFrame(False)
        self._line_edit.setClearButtonEnabled(True)
        self._line_edit.setPlaceholderText("")
        self._line_edit.textEdited.connect(self._on_text_edited)
        self._line_edit.returnPressed.connect(self._commit_current)
        self._layout.addWidget(self._line_edit, 1)

        # Tab で確定
        self._line_edit.installEventFilter(self)

        self.setFocusProxy(self._line_edit)
        self._apply_styles()
        self._refresh_placeholder()

        try:
            ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    def _on_theme_changed(self, *_args) -> None:
        try:
            self._apply_styles()
        except Exception:
            pass

    def eventFilter(self, obj, event):  # type: ignore[override]
        if obj is self._line_edit and event.type() == event.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Enter, Qt.Key.Key_Return):
                self._commit_current()
                return True
        return super().eventFilter(obj, event)

    def _apply_styles(self) -> None:
        # 外枠は INPUT の見た目に寄せる
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 4px;
            }}
            QLineEdit {{
                background: transparent;
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: none;
                padding: 2px;
                min-height: 18px;
            }}
            QPushButton[tagChip="true"] {{
                background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_NEUTRAL_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_NEUTRAL_BORDER)};
                border-radius: 10px;
                padding: 1px 8px;
                font-size: 9.5pt;
            }}
            QPushButton[tagChip="true"]:hover {{
                background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER)};
            }}
            """
        )

    def _normalize_tag(self, raw: str) -> str:
        return raw.strip()

    def _add_tag(self, tag: str) -> None:
        normalized = self._normalize_tag(tag)
        if not normalized:
            return
        if normalized in self._tags:
            return
        self._tags.append(normalized)
        self._rebuild_chips()
        self.textChanged.emit(self.text())

    def _remove_tag(self, tag: str) -> None:
        try:
            self._tags.remove(tag)
        except ValueError:
            return
        self._rebuild_chips()
        self.textChanged.emit(self.text())

    def _rebuild_chips(self) -> None:
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for tag in self._tags:
            chip = QPushButton(self._chips_container)
            chip.setProperty("tagChip", "true")
            chip.setText(f"{tag} ×")
            chip.setToolTip(tag)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, t=tag: self._remove_tag(t))

            self._chips_layout.addWidget(chip)

        self._chips_layout.addStretch(1)
        self._refresh_placeholder()

    def _refresh_placeholder(self) -> None:
        # タグがある場合はプレースホルダーは消して視認性を上げる
        self._line_edit.setPlaceholderText(self._placeholder_text if not self._tags else "")

    def _on_text_edited(self, text: str) -> None:
        if "," not in text:
            self.textChanged.emit(self.text())
            return

        parts = text.split(",")
        for p in parts[:-1]:
            self._add_tag(p)

        self._line_edit.setText(parts[-1].lstrip())
        self.textChanged.emit(self.text())

    def _commit_current(self) -> None:
        current = self._line_edit.text()
        if current:
            self._add_tag(current)
            self._line_edit.clear()
        else:
            self.textChanged.emit(self.text())

    # --- QLineEdit互換API ---
    def text(self) -> str:  # type: ignore[override]
        current = self._normalize_tag(self._line_edit.text())
        tags = list(self._tags)
        if current:
            tags.append(current)
        return ",".join(tags)

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._tags = []
        if text:
            for t in text.split(","):
                normalized = self._normalize_tag(t)
                if normalized and normalized not in self._tags:
                    self._tags.append(normalized)
        self._line_edit.clear()
        self._rebuild_chips()
        self.textChanged.emit(self.text())

    def setPlaceholderText(self, text: str) -> None:  # type: ignore[override]
        self._placeholder_text = text or ""
        self._refresh_placeholder()

    def setEnabled(self, enabled: bool) -> None:  # type: ignore[override]
        super().setEnabled(enabled)
        self._line_edit.setEnabled(enabled)
        # チップ内ボタンもまとめて disable
        for child in self._chips_container.findChildren(QPushButton):
            child.setEnabled(enabled)

    # テスト/利用者向け: 内部LineEditを取得したい場合
    def _get_line_edit(self) -> QLineEdit:
        return self._line_edit
