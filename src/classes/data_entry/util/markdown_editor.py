import logging
import re

from qt_compat.widgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTextEdit, QPushButton
from qt_compat.core import Qt, Signal, QTimer
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

    MODE_NORMAL = 1
    MODE_INPUT_ONLY = 2
    MODE_PREVIEW_ONLY = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = self.MODE_NORMAL
        self._preview_debounce_ms = 250
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._update_preview)
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
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)

        # --- 左: ボタン群（コンパクト） ---
        self._button_panel = QWidget()
        button_layout = QGridLayout(self._button_panel)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setHorizontalSpacing(4)
        button_layout.setVerticalSpacing(4)

        # 最小限のツールボタン
        self.btn_bold = self._create_tool_button("B", "太字 (**text**)", self._insert_bold, font_bold=True)
        self.btn_italic = self._create_tool_button("I", "斜体 (*text*)", self._insert_italic, font_italic=True)

        # 行スタイル（1行1スタイル対象: 太字/斜体は除外）
        self.btn_h1 = self._create_tool_button("H1", "見出し1 (# text)", lambda: self._toggle_line_style(self.MODE_NORMAL, "h1"))
        self.btn_h2 = self._create_tool_button("H2", "見出し2 (## text)", lambda: self._toggle_line_style(self.MODE_NORMAL, "h2"))
        self.btn_h3 = self._create_tool_button("H3", "見出し3 (### text)", lambda: self._toggle_line_style(self.MODE_NORMAL, "h3"))
        self.btn_quote = self._create_tool_button(
            "",
            "引用 (> text)",
            lambda: self._toggle_line_style(self.MODE_NORMAL, "quote"),
            icon_sp=(QStyle.StandardPixmap.SP_MessageBoxInformation if QStyle is not None else None),
        )
        self.btn_list = self._create_tool_button(
            "",
            "リスト (- item)",
            lambda: self._toggle_line_style(self.MODE_NORMAL, "list"),
            icon_sp=(QStyle.StandardPixmap.SP_FileDialogListView if QStyle is not None else None),
        )
        self.btn_olist = self._create_tool_button(
            "",
            "数値リスト (1. item)",
            lambda: self._toggle_line_style(self.MODE_NORMAL, "olist"),
            icon_sp=(QStyle.StandardPixmap.SP_FileDialogDetailedView if QStyle is not None else None),
        )
        self.btn_link = self._create_tool_button(
            "",
            "リンク ([text](url))",
            self._insert_link,
            icon_sp=(QStyle.StandardPixmap.SP_DirLinkIcon if QStyle is not None else None),
        )

        # 表示モード切替（1ボタン巡回）
        self.btn_preview = QPushButton("")
        self.btn_preview.setToolTip("表示モード切替: 通常 → 入力専用 → プレビュー専用")
        self.btn_preview.setFixedWidth(30)
        try:
            if QStyle is not None:
                self.btn_preview.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        except Exception:
            pass
        self.btn_preview.clicked.connect(self._cycle_mode)

        # 3列で配置（ボタン群は4行: 3行 + モード切替1行）
        buttons = [
            self.btn_bold,
            self.btn_italic,
            self.btn_h1,
            self.btn_h2,
            self.btn_h3,
            self.btn_quote,
            self.btn_list,
            self.btn_olist,
            self.btn_link,
        ]
        columns = 3
        r = 0
        c = 0
        for b in buttons:
            button_layout.addWidget(b, r, c)
            c += 1
            if c >= columns:
                c = 0
                r += 1

        button_layout.addWidget(self.btn_preview, r + 1, 0, 1, columns)

        # --- 中: 入力 / 右: プレビュー（同幅） ---
        self.editor = QTextEdit()
        # QAbstractScrollArea系は環境によってQSSのborderが描画されないことがあるため、
        # StyledBackgroundを有効化して枠線描画を確実にする。
        try:
            self.editor.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            # border/background は viewport 側に描画する方針のため、viewportもStyledBackground対象にする
            self.editor.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass
        self.editor.setPlaceholderText("説明を入力してください。（マークダウン記法が使えます）")
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.cursorPositionChanged.connect(self._on_cursor_position_changed)

        # 横スクロールしない
        try:
            self.editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            self.editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        except Exception:
            pass

        from qt_compat.widgets import QTextBrowser

        self.preview = QTextBrowser()
        try:
            self.preview.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            self.preview.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        except Exception:
            pass
        self.preview.setOpenExternalLinks(True)
        self.preview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.preview.setVisible(True)

        try:
            self.preview.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            self.preview.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        except Exception:
            pass

        main_layout.addWidget(self._button_panel)
        main_layout.addWidget(self.editor, 1)
        main_layout.addWidget(self.preview, 1)

        # 高さは「7行程度」に寄せる（入力・プレビュー同じ高さ）
        try:
            line_h = self.editor.fontMetrics().lineSpacing()
            target_h = int(line_h * 7+ 14)
            self.editor.setFixedHeight(target_h)
            self.preview.setFixedHeight(target_h)
            self._button_panel.setFixedHeight(target_h)
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

        self._update_mode_visibility()
        self._update_preview_debounced(force=True)
        self._update_line_style_indicator()

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
        btn.setFixedWidth(30)
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
        self._tool_button_qss = f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_NEUTRAL_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_NEUTRAL_BORDER)};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 9.5pt;
                min-height: 20px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER)};
            }}
        """

        self._tool_button_active_qss = f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 9.5pt;
                min-height: 20px;
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
            btn.setStyleSheet(self._tool_button_qss)

        if self.btn_preview is not None and (isValid is None or isValid(self.btn_preview)):
            self.btn_preview.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
                border-radius: 4px;
                padding: 2px 6px;
                font-weight: 600;
                font-size: 9.5pt;
                min-height: 20px;
            }}
            """
            )

        # NOTE:
        # 入力欄/プレビュー欄の枠線・背景・文字色は「アプリ全体のグローバルQSS」が正。
        # ローカル setStyleSheet で上書きすると、テーマ集約の妨げ & 競合の原因になり得るため、ここでは適用しない。

        # Markdownプレビューの「コンテンツ装飾（見出し・コードなど）」のみ例外として document 側の CSS で適用。
        # これはウィジェットの border/background とは独立しており、グローバルQSSと競合しにくい。
        if self.preview is not None and (isValid is None or isValid(self.preview)):
            try:
                preview_css = f"""
                body {{
                    color: {get_color(ThemeKey.TEXT_PRIMARY)};
                }}
                a {{
                    color: {get_color(ThemeKey.TEXT_LINK)};
                }}
                h1, h2, h3 {{
                    color: {get_color(ThemeKey.TEXT_PRIMARY)};
                }}
                h1 {{
                    border-bottom: 1px solid {get_color(ThemeKey.SEPARATOR_DEFAULT)};
                    padding-bottom: 4px;
                }}
                pre {{
                    background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};
                    border: 1px solid {get_color(ThemeKey.BORDER_LIGHT)};
                    padding: 6px;
                    border-radius: 4px;
                    white-space: pre-wrap;
                }}
                code {{
                    background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};
                }}
                blockquote {{
                    border-left: 3px solid {get_color(ThemeKey.BORDER_DEFAULT)};
                    margin-left: 0;
                    padding-left: 10px;
                    color: {get_color(ThemeKey.TEXT_MUTED)};
                }}
                """
                self.preview.document().setDefaultStyleSheet(preview_css)
            except Exception:
                pass
            

        self._update_line_style_indicator()
        from qt_compat.widgets import QApplication

        logger.debug("editor.styleSheet = %r", self.editor.styleSheet())
        logger.debug("app.styleSheet(head) = %r", (QApplication.instance().styleSheet()[:500] if QApplication.instance() else None))
        logger.debug("editor.palette.Base = %r", self.editor.palette().color(self.editor.palette().ColorRole.Base).name())
        logger.debug("viewport.styleSheet = %r", self.editor.viewport().styleSheet())



    def _on_theme_changed(self, *_args) -> None:
        if isValid is not None and not isValid(self):
            return
        self._apply_styles()
        self._update_preview_debounced(force=True)

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
        self._toggle_line_prefix(prefix)

    def _insert_list(self) -> None:
        self._toggle_line_prefix("- ")

    def _insert_ordered_list(self) -> None:
        self._toggle_line_prefix("1. ")

    def _insert_quote(self) -> None:
        self._toggle_line_prefix("> ")

    def _insert_link(self) -> None:
        self._insert_text("[", "](url)")

    def _cycle_mode(self) -> None:
        if self._mode == self.MODE_NORMAL:
            self._mode = self.MODE_INPUT_ONLY
        elif self._mode == self.MODE_INPUT_ONLY:
            self._mode = self.MODE_PREVIEW_ONLY
        else:
            self._mode = self.MODE_NORMAL
        self._update_mode_visibility()
        self._update_preview_debounced(force=True)

    def _update_mode_visibility(self) -> None:
        is_input = self._mode in (self.MODE_NORMAL, self.MODE_INPUT_ONLY)
        is_preview = self._mode in (self.MODE_NORMAL, self.MODE_PREVIEW_ONLY)

        self.editor.setVisible(is_input)
        self.preview.setVisible(is_preview)

        # プレビュー専用時は編集不可（入力欄が見えないため）
        try:
            self.editor.setReadOnly(not is_input)
        except Exception:
            pass

        # 入力欄が見えているときのみスタイルボタンを有効化
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
                    btn.setEnabled(is_input)
            except Exception:
                pass

    def _on_text_changed(self) -> None:
        self.textChanged.emit()
        self._update_preview_debounced()
        self._update_line_style_indicator()

    def _on_cursor_position_changed(self) -> None:
        self._update_line_style_indicator()

    def _update_preview_debounced(self, *, force: bool = False) -> None:
        if force:
            try:
                self._preview_timer.stop()
            except Exception:
                pass
            self._update_preview()
            return
        try:
            self._preview_timer.start(self._preview_debounce_ms)
        except Exception:
            self._update_preview()

    def _update_preview(self) -> None:
        markdown_text = self.editor.toPlainText().strip() or "内容がありません"
        try:
            self.preview.document().setMarkdown(markdown_text)
        except Exception:
            self.preview.setPlainText(markdown_text)

    def _detect_line_style(self, line_text: str) -> str | None:
        if line_text.startswith("### "):
            return "h3"
        if line_text.startswith("## "):
            return "h2"
        if line_text.startswith("# "):
            return "h1"
        if line_text.startswith("> "):
            return "quote"
        if line_text.startswith("- "):
            return "list"
        if re.match(r"^\d+\. ", line_text):
            return "olist"
        return None

    def _strip_any_line_style_prefix(self, line_text: str) -> tuple[str, str | None, int]:
        current = self._detect_line_style(line_text)
        if current is None:
            return line_text, None, 0
        prefixes = {
            "h1": "# ",
            "h2": "## ",
            "h3": "### ",
            "quote": "> ",
            "list": "- ",
        }
        if current in prefixes:
            p = prefixes[current]
            return line_text[len(p):], current, len(p)
        # ordered list
        m = re.match(r"^(\d+\. )", line_text)
        if m:
            p = m.group(1)
            return line_text[len(p):], "olist", len(p)
        return line_text, None, 0

    def _toggle_line_prefix(self, desired_prefix: str) -> None:
        # 後方互換（未使用）: プレフィックスを直接トグル
        style_map = {
            "# ": "h1",
            "## ": "h2",
            "### ": "h3",
            "> ": "quote",
            "- ": "list",
            "1. ": "olist",
        }
        style = style_map.get(desired_prefix)
        if style is None:
            self._insert_text(desired_prefix)
            return
        self._apply_or_remove_line_style(style)

    def _toggle_line_style(self, _unused_mode: int, style: str) -> None:
        self._apply_or_remove_line_style(style)

    def _apply_or_remove_line_style(self, style: str) -> None:
        if not self.editor.isVisible():
            return

        cursor = self.editor.textCursor()
        block = cursor.block()
        block_start = block.position()
        col = cursor.position() - block_start

        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        line_text = cursor.selectedText() or ""

        stripped, current_style, removed_prefix_len = self._strip_any_line_style_prefix(line_text)
        desired_prefix = {
            "h1": "# ",
            "h2": "## ",
            "h3": "### ",
            "quote": "> ",
            "list": "- ",
            "olist": "1. ",
        }[style]
        desired_prefix_len = len(desired_prefix)

        applying = current_style != style
        if applying:
            new_line = f"{desired_prefix}{stripped}"
            delta = -removed_prefix_len + desired_prefix_len
        else:
            new_line = stripped
            delta = -removed_prefix_len

        cursor.insertText(new_line)
        self.editor.setFocus()

        # カーソル位置を“同じ見た目の列”に寄せる
        new_col = max(0, col + delta)
        try:
            c2 = self.editor.textCursor()
            c2.setPosition(block_start + min(new_col, len(new_line)))
            self.editor.setTextCursor(c2)
        except Exception:
            pass

        # スタイル適用時は必ず改行（空行が次にある場合はそこへ移動）
        if applying:
            try:
                c3 = self.editor.textCursor()
                c3.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                next_block = c3.block().next()
                if next_block.isValid() and next_block.text() == "":
                    c3.movePosition(QTextCursor.MoveOperation.NextBlock)
                else:
                    c3.insertBlock()
                self.editor.setTextCursor(c3)
            except Exception:
                pass

        self._update_line_style_indicator()
        self._update_preview_debounced()

    def _update_line_style_indicator(self) -> None:
        if not hasattr(self, "editor") or self.editor is None:
            return
        if not self.editor.isVisible():
            for btn in [self.btn_h1, self.btn_h2, self.btn_h3, self.btn_quote, self.btn_list, self.btn_olist]:
                if btn is None:
                    continue
                btn.setProperty("active", False)
                if hasattr(self, "_tool_button_qss"):
                    btn.setStyleSheet(self._tool_button_qss)
            return

        cursor = self.editor.textCursor()
        block_text = cursor.block().text() or ""
        current = self._detect_line_style(block_text)

        mapping = {
            "h1": self.btn_h1,
            "h2": self.btn_h2,
            "h3": self.btn_h3,
            "quote": self.btn_quote,
            "list": self.btn_list,
            "olist": self.btn_olist,
        }

        for style, btn in mapping.items():
            if btn is None:
                continue
            is_active = current == style
            btn.setProperty("active", is_active)
            if hasattr(self, "_tool_button_active_qss") and hasattr(self, "_tool_button_qss"):
                btn.setStyleSheet(self._tool_button_active_qss if is_active else self._tool_button_qss)

    def setText(self, text: str) -> None:
        self.editor.setText(text)
        self._update_preview_debounced(force=True)

    def toPlainText(self) -> str:
        return self.editor.toPlainText()

    def setPlaceholderText(self, text: str) -> None:
        self.editor.setPlaceholderText(text)
