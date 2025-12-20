import logging

from qt_compat.widgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton
from qt_compat.core import Qt, Signal
from qt_compat.gui import QTextCursor

try:
    from PySide6.QtWidgets import QStyle  # type: ignore
except Exception:  # pragma: no cover
    QStyle = None  # type: ignore

try:
    from shiboken6 import isValid  # type: ignore
except Exception:  # pragma: no cover
    isValid = None  # type: ignore

from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import ThemeManager, get_color

logger = logging.getLogger(__name__)


class MarkdownEditor(QWidget):
    """マークダウンエディタ（シンプル版）

    - 編集: QTextEdit
    - プレビュー: QTextBrowser (Qtの Markdown レンダリング: QTextDocument.setMarkdown)
    - 切替: ボタンで編集↔プレビュー

    要件:
    - プレビューは「レンダリング結果」を表示（mdテキストそのものではない）
    - テーマ準拠（ライト: 明背景+暗文字 / ダーク: 暗背景+明文字）
    - テーマ切替時はスタイル再適用 + プレビュー更新
    """

    textChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_preview = False
        self._setup_ui()
        self._apply_styles()

        try:
            # NOTE: lambda を使うと receiver が MarkdownEditor にならず、
            # ウィジェット破棄後も接続が残って「Internal C++ object already deleted」になり得る。
            # bound method に直接接続すれば Qt 側で破棄時に自動的に切断される。
            ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(4)

        # 最小限のツールバー
        self.btn_bold = self._create_tool_button("B", "太字 (**text**)", self._insert_bold, font_bold=True)
        self.btn_italic = self._create_tool_button("I", "斜体 (*text*)", self._insert_italic, font_italic=True)
        self.btn_h1 = self._create_tool_button("H1", "見出し (# text)", lambda: self._insert_header(1))
        self.btn_h2 = self._create_tool_button("H2", "見出し (## text)", lambda: self._insert_header(2))
        self.btn_h3 = self._create_tool_button("H3", "見出し (### text)", lambda: self._insert_header(3))
        self.btn_quote = self._create_tool_button("", "引用 (> text)", self._insert_quote, icon_sp=(QStyle.StandardPixmap.SP_MessageBoxInformation if QStyle is not None else None))
        self.btn_list = self._create_tool_button("", "リスト (- item)", self._insert_list, icon_sp=(QStyle.StandardPixmap.SP_FileDialogListView if QStyle is not None else None))
        self.btn_olist = self._create_tool_button("", "数値リスト (1. item)", self._insert_ordered_list, icon_sp=(QStyle.StandardPixmap.SP_FileDialogDetailedView if QStyle is not None else None))
        self.btn_link = self._create_tool_button("", "リンク ([text](url))", self._insert_link, icon_sp=(QStyle.StandardPixmap.SP_DirLinkIcon if QStyle is not None else None))

        for btn in [
            self.btn_bold,
            self.btn_italic,
            self.btn_h1,
            self.btn_h2,
            self.btn_h3,
            self.btn_quote,
            self.btn_list,
            self.btn_olist,
            self.btn_link,
        ]:
            toolbar_layout.addWidget(btn)

        toolbar_layout.addStretch()

        self.btn_preview = QPushButton("")
        self.btn_preview.setCheckable(True)
        self.btn_preview.setToolTip("プレビュー表示/非表示")
        self.btn_preview.setFixedWidth(34)
        try:
            if QStyle is not None:
                self.btn_preview.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        except Exception:
            pass
        self.btn_preview.clicked.connect(self._toggle_preview)
        toolbar_layout.addWidget(self.btn_preview)

        main_layout.addLayout(toolbar_layout)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("マークダウンを入力してください...")
        self.editor.textChanged.connect(self._on_text_changed)

        from qt_compat.widgets import QTextBrowser

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.preview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.preview.setVisible(False)

        main_layout.addWidget(self.editor)
        main_layout.addWidget(self.preview)

        # 高さは「7行程度」に寄せる（入力・プレビュー同じ高さ）
        try:
            line_h = self.editor.fontMetrics().lineSpacing()
            target_h = int(line_h * 7+ 14)
            self.editor.setFixedHeight(target_h)
            self.preview.setFixedHeight(target_h)
        except Exception:
            pass

        # 入力欄とプレビュー欄のスクロールを同期
        self._syncing_scroll = False

        def _sync_from_editor(v: int) -> None:
            if self._syncing_scroll:
                return
            if not self._is_preview:
                return
            self._syncing_scroll = True
            try:
                self.preview.verticalScrollBar().setValue(v)
            finally:
                self._syncing_scroll = False

        def _sync_from_preview(v: int) -> None:
            if self._syncing_scroll:
                return
            if not self._is_preview:
                return
            self._syncing_scroll = True
            try:
                self.editor.verticalScrollBar().setValue(v)
            finally:
                self._syncing_scroll = False

        try:
            self.editor.verticalScrollBar().valueChanged.connect(_sync_from_editor)
            self.preview.verticalScrollBar().valueChanged.connect(_sync_from_preview)
        except Exception:
            pass

    def _create_tool_button(
        self,
        text: str,
        tooltip: str,
        callback,
        *,
        font_bold: bool = False,
        font_italic: bool = False,
        icon_sp=None,
    ) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setFixedWidth(34)
        try:
            f = btn.font()
            if font_bold:
                f.setBold(True)
            if font_italic:
                f.setItalic(True)
            btn.setFont(f)
        except Exception:
            pass

        try:
            if QStyle is not None and icon_sp is not None:
                btn.setIcon(self.style().standardIcon(icon_sp))
        except Exception:
            pass
        btn.clicked.connect(callback)
        return btn

    def _apply_styles(self) -> None:
        tool_button_qss = f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_NEUTRAL_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_NEUTRAL_BORDER)};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 9.5pt;
                min-height: 22px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER)};
            }}
        """
        for btn in [
            self.btn_bold,
            self.btn_italic,
            self.btn_h1,
            self.btn_h2,
            self.btn_h3,
            self.btn_quote,
            self.btn_list,
            self.btn_olist,
            self.btn_link,
        ]:
            if btn is None:
                continue
            if isValid is not None and not isValid(btn):
                continue
            btn.setStyleSheet(tool_button_qss)

        if self.btn_preview is not None and (isValid is None or isValid(self.btn_preview)):
            self.btn_preview.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
                border-radius: 4px;
                padding: 2px 10px;
                font-weight: 600;
                font-size: 9.5pt;
                min-height: 22px;
            }}
            QPushButton:checked {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};
            }}
            """
            )

        if self.editor is not None and (isValid is None or isValid(self.editor)):
            self.editor.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 4px;
                padding: 6px;
            }}
            """
            )

        if self.preview is not None and (isValid is None or isValid(self.preview)):
            self.preview.setStyleSheet(
            f"""
            QTextBrowser {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
                border: 1px solid {get_color(ThemeKey.INPUT_BORDER)};
                border-radius: 4px;
                padding: 6px;
            }}
            """
            )

    def _on_theme_changed(self, *_args) -> None:
        if isValid is not None and not isValid(self):
            return
        self._apply_styles()
        if self._is_preview:
            self._update_preview()

    def _insert_text(self, prefix: str, suffix: str = "") -> None:
        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText()

        if not selected_text:
            cursor.insertText(f"{prefix}{suffix}")
            if suffix:
                cursor.movePosition(
                    QTextCursor.MoveOperation.Left,
                    QTextCursor.MoveMode.MoveAnchor,
                    len(suffix),
                )
                self.editor.setTextCursor(cursor)
        else:
            cursor.insertText(f"{prefix}{selected_text}{suffix}")

        self.editor.setFocus()

    def _insert_bold(self) -> None:
        self._insert_text("**", "**")

    def _insert_italic(self) -> None:
        self._insert_text("*", "*")

    def _insert_header(self, level: int) -> None:
        prefix = "#" * level + " "
        self._insert_text(prefix)

    def _insert_list(self) -> None:
        self._insert_text("- ")

    def _insert_ordered_list(self) -> None:
        self._insert_text("1. ")

    def _insert_quote(self) -> None:
        self._insert_text("> ")

    def _insert_link(self) -> None:
        self._insert_text("[", "](url)")

    def _toggle_preview(self) -> None:
        self._is_preview = self.btn_preview.isChecked()
        self.preview.setVisible(self._is_preview)
        # 入力欄とプレビュー欄は分離して表示（入力欄は常に表示）
        self.editor.setVisible(True)

        # プレビュー表示中は「スタイル適用ボタン」と「テキストエリア入力」を無効化
        try:
            self.editor.setReadOnly(self._is_preview)
        except Exception:
            pass
        for btn in [
            self.btn_bold,
            self.btn_italic,
            self.btn_h1,
            self.btn_h2,
            self.btn_h3,
            self.btn_quote,
            self.btn_list,
            self.btn_olist,
            self.btn_link,
        ]:
            try:
                if btn is not None:
                    btn.setEnabled(not self._is_preview)
            except Exception:
                pass

        if self._is_preview:
            self._update_preview()

    def _on_text_changed(self) -> None:
        self.textChanged.emit()
        if self._is_preview:
            self._update_preview()

    def _update_preview(self) -> None:
        markdown_text = self.editor.toPlainText().strip() or "内容がありません"
        try:
            self.preview.document().setMarkdown(markdown_text)
        except Exception:
            self.preview.setPlainText(markdown_text)

    def setText(self, text: str) -> None:
        self.editor.setText(text)
        if self._is_preview:
            self._update_preview()

    def toPlainText(self) -> str:
        return self.editor.toPlainText()

    def setPlaceholderText(self, text: str) -> None:
        self.editor.setPlaceholderText(text)
