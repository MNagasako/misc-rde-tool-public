"""更新履歴タブ - リリースノート表示"""

import logging

logger = logging.getLogger(__name__)

try:
    from qt_compat.widgets import QWidget, QVBoxLayout, QTextBrowser, QGroupBox
    from qt_compat.core import Qt
    from classes.theme import ThemeKey
    from classes.theme import ThemeManager, get_color

    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False

    class QWidget:  # type: ignore[no-redef]
        pass


from classes.help.util.markdown_renderer import load_help_markdown, set_markdown_document


class ReleaseNotesTab(QWidget):
    """更新履歴タブ"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

        # Theme: markdownの装飾は QTextDocument の default CSS で適用する。
        # (QTextBrowser 自体の背景/枠線はグローバルQSSに委ねる)
        self._bind_theme_refresh()
        self._apply_markdown_style()

    def _apply_markdown_style(self) -> None:
        try:
            browser = getattr(self, "_browser", None)
            if browser is None:
                return
            document = browser.document()

            css = f"""
            body {{
                color: {get_color(ThemeKey.TEXT_PRIMARY)};
            }}
            a {{
                color: {get_color(ThemeKey.TEXT_LINK)};
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
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
            table {{
                border-collapse: collapse;
            }}
            th, td {{
                border: 1px solid {get_color(ThemeKey.BORDER_LIGHT)};
                padding: 4px 6px;
            }}
            th {{
                background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};
            }}
            """
            document.setDefaultStyleSheet(css)
        except Exception:
            pass

    def _bind_theme_refresh(self) -> None:
        try:
            tm = ThemeManager.instance()
        except Exception:
            return

        def _on_theme_changed(*_args) -> None:
            try:
                self._apply_markdown_style()
            except Exception:
                pass

        try:
            tm.theme_changed.connect(_on_theme_changed)
        except Exception:
            return

        # Keep a reference so the slot isn't GC'd.
        try:
            self._rde_theme_refresh_slot = _on_theme_changed  # type: ignore[attr-defined]
        except Exception:
            pass

        def _disconnect(*_args) -> None:
            try:
                tm.theme_changed.disconnect(_on_theme_changed)
            except Exception:
                pass

        try:
            self.destroyed.connect(_disconnect)
        except Exception:
            pass

    def setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        group = QGroupBox("更新履歴")
        group_layout = QVBoxLayout(group)

        self._group = QGroupBox("更新履歴")
        group_layout = QVBoxLayout(self._group)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        try:
            self._browser.document().setDocumentMargin(8)
        except Exception:
            pass

        try:
            text, base_dir = load_help_markdown("release_notes.md")
            set_markdown_document(self._browser, text, base_dir)
        except FileNotFoundError as e:
            logger.warning("更新履歴ファイルが見つかりません: %s", e)
            self._browser.setPlainText(
                "更新履歴ファイルが見つかりませんでした。src/resources/docs/help/release_notes.md を確認してください。"
            )
        except Exception as e:
            logger.error("更新履歴読み込みエラー: %s", e)
            self._browser.setPlainText(f"更新履歴の読み込みに失敗しました。\n\nエラー: {e}")

        group_layout.addWidget(self._browser)
        layout.addWidget(self._group)


def create_release_notes_tab(parent=None):
    """更新履歴タブを作成"""
    try:
        if not PYQT5_AVAILABLE:
            return None
        return ReleaseNotesTab(parent)
    except Exception as e:
        logger.error("更新履歴タブ作成エラー: %s", e)
        return None
