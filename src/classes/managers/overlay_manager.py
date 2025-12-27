"""Data-fetch WebView overlay (DOM injection).

Windows + QWebEngineView has well-known composition issues with translucent
QWidgets layered above the WebEngine surface (ghosting/double draw on move).

To prioritize eliminating "double overlay" artifacts, this module implements
the overlay inside the WebEngine DOM by injecting HTML/CSS/JS.

Constraints:
- Shown only for the data-fetch screen (mode == 'data_fetch')
- Never shown for request_analyzer
- Uses theme colors (ThemeKey.*) and bundled Nanote images
"""

from __future__ import annotations

import base64
import json

from qt_compat.core import QEvent
from qt_compat.widgets import QWidget

from classes.managers.log_manager import get_logger
from classes.theme import ThemeKey, ThemeManager, get_color
from config.common import get_static_resource_path

logger = get_logger("RDE_WebView")


class OverlayManager:
    """Manage a DOM-injected overlay for the data_fetch WebView."""

    _DOM_ID = "rde_webview_overlay"

    def __init__(self, parent: QWidget, webview: QWidget):
        self.parent = parent
        self.webview = webview

        # Public attribute kept for backward compatibility with older tests/callers.
        # In DOM mode we don't create an overlay QWidget.
        self.overlay = None

        self._enabled: bool = False
        self._last_text: str = ""
        self._nanote_data_urls: list[str] = []

        # Keep overlay style updated on theme changes.
        try:
            ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

        # Re-inject after navigations, because DOM is replaced.
        try:
            page = self._page()
            if page is not None and hasattr(page, "loadFinished"):
                page.loadFinished.connect(self._on_load_finished)
        except Exception:
            pass

    def _page(self):
        try:
            # Avoid shiboken6.isValid() here.
            # In long-running widget test suites, calling into shiboken for validity
            # checks can occasionally crash the interpreter when Qt objects are in a
            # transitional state during teardown. It's safer to just try/except and
            # treat any runtime errors as "no page".
            if self.webview is None:
                return None
            if not hasattr(self.webview, "page"):
                return None
            return self.webview.page()
        except Exception:
            return None

    def _run_js(self, js: str) -> None:
        try:
            page = self._page()
            if page is None or not hasattr(page, "runJavaScript"):
                return
            page.runJavaScript(js)
        except Exception:
            return

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            return
        # If overlay is active, re-apply it on the new document.
        if self._enabled and self._should_show_overlay_now():
            self._apply_overlay_dom(show=True, text=self._last_text or self._default_message())

    def _on_theme_changed(self, *_args):
        # Update DOM styles without toggling visibility.
        if self._enabled and self._should_show_overlay_now():
            self._apply_overlay_dom(show=True, text=self._last_text or self._default_message())

    def _should_show_overlay_now(self) -> bool:
        modes: list[str] = []
        try:
            mode = getattr(self.parent, "current_mode", None)
            if isinstance(mode, str):
                modes.append(mode)
        except Exception:
            pass

        try:
            ui_controller = getattr(self.parent, "ui_controller", None)
            mode2 = getattr(ui_controller, "current_mode", None)
            if isinstance(mode2, str):
                modes.append(mode2)
        except Exception:
            pass

        if not modes:
            # Tests or simple parents.
            return True

        # Explicitly exclude request_analyzer.
        if "request_analyzer" in modes:
            return False

        return "data_fetch" in modes

    def _default_message(self) -> str:
        return (
            "閲覧専用/操作不可\n"
            "このウインドウは自動処理に必要なため表示しています。\n"
            "操作すると正しく動作しない場合があります\n"
            "画像数が多いと時間がかかります\n"
        )

    def _ensure_nanote_data_urls(self) -> None:
        if self._nanote_data_urls:
            return

        rel_paths = [
            "image/nanote_01.png",
            "image/nanote_02.png",
            "image/nanote_03.png",
            "image/nanote_04.png",
        ]
        urls: list[str] = []
        for rel in rel_paths:
            try:
                abs_path = get_static_resource_path(rel)
                raw = open(abs_path, "rb").read()
                b64 = base64.b64encode(raw).decode("ascii")
                urls.append(f"data:image/png;base64,{b64}")
            except Exception:
                urls.append("")
        self._nanote_data_urls = urls

    def _apply_overlay_dom(self, *, show: bool, text: str) -> None:
        """Inject/remove overlay element in the current document."""
        # Theme colors must come from ThemeKey (no new hard-coded colors here).
        bg = get_color(ThemeKey.OVERLAY_BACKGROUND)
        fg = get_color(ThemeKey.OVERLAY_TEXT)

        self._ensure_nanote_data_urls()

        payload = {
            "id": self._DOM_ID,
            "show": bool(show),
            "text": text or "",
            "bg": bg,
            "fg": fg,
            "nanote": self._nanote_data_urls,
        }

        # Use JSON to avoid injection issues (newlines/quotes).
        data_json = json.dumps(payload, ensure_ascii=False)

        js = (
            "(function(){"
            f"const d={data_json};"
            "try{"
            "  const id=d.id;"
            "  const old=document.getElementById(id);"
            "  if(old){ old.remove(); }"
            "  if(!d.show){ return; }"
            "  const root=document.body || document.documentElement;"
            "  if(!root){ return; }"
            "  const overlay=document.createElement('div');"
            "  overlay.id=id;"
            "  overlay.setAttribute('data-rde-overlay','1');"
            "  overlay.style.position='fixed';"
            "  overlay.style.left='0';"
            "  overlay.style.top='0';"
            "  overlay.style.width='100vw';"
            "  overlay.style.height='100vh';"
            "  overlay.style.zIndex='2147483647';"
            "  overlay.style.pointerEvents='auto';"
            "  overlay.style.backgroundColor=d.bg;"
            "  overlay.style.display='block';"
            "  overlay.style.userSelect='none';"
            "  overlay.style.webkitUserSelect='none';"
            "  overlay.style.overflow='hidden';"
            "  const size=120;"
            "  function addCorner(src,left,top,right,bottom){"
            "    if(!src){ return; }"
            "    const img=document.createElement('img');"
            "    img.src=src;"
            "    img.alt='';"
            "    img.style.position='absolute';"
            "    img.style.width=size+'px';"
            "    img.style.height=size+'px';"
            "    if(left!==null){ img.style.left=left; }"
            "    if(top!==null){ img.style.top=top; }"
            "    if(right!==null){ img.style.right=right; }"
            "    if(bottom!==null){ img.style.bottom=bottom; }"
            "    overlay.appendChild(img);"
            "  }"
            "  const n=d.nanote||[];"
            "  addCorner(n[0]||'', '0', '0', null, null);"
            "  addCorner(n[1]||'', null, '0', '0', null);"
            "  addCorner(n[2]||'', '0', null, null, '0');"
            "  addCorner(n[3]||'', null, null, '0', '0');"
            "  const msg=document.createElement('div');"
            "  msg.style.position='absolute';"
            "  msg.style.left='50%';"
            "  msg.style.top='50%';"
            "  msg.style.transform='translate(-50%, -50%)';"
            "  msg.style.textAlign='center';"
            "  msg.style.whiteSpace='pre-line';"
            "  msg.style.fontWeight='700';"
            "  msg.style.fontSize='28px';"
            "  msg.style.lineHeight='1.35';"
            "  msg.style.color=d.fg;"
            "  msg.textContent=d.text;"
            "  overlay.appendChild(msg);"
            "  root.appendChild(overlay);"
            "}catch(e){ /* ignore */ }"
            "})();"
        )

        self._run_js(js)

    def debug_dump_overlays(self) -> None:
        # DOM overlay; we can only log local state here.
        try:
            logger.info("[OverlayDump] dom_enabled=%s", self._enabled)
        except Exception:
            return

    def show_overlay(self, watermark_text: str | None = None) -> None:
        if not self._should_show_overlay_now():
            try:
                logger.debug("[Overlay] show skipped (mode=%s)", getattr(self.parent, "current_mode", None))
            except Exception:
                pass
            return

        self._enabled = True
        self._last_text = watermark_text or self._default_message()
        self._apply_overlay_dom(show=True, text=self._last_text)

    def hide_overlay(self) -> None:
        self._enabled = False
        self._apply_overlay_dom(show=False, text="")

    def is_overlay_visible(self) -> bool:
        return bool(self._enabled)

    def resize_overlay(self) -> None:
        # DOM overlay uses viewport sizing; no geometry work needed.
        if self._enabled and self._should_show_overlay_now():
            # Re-apply to ensure the element exists after any navigation.
            self._apply_overlay_dom(show=True, text=self._last_text or self._default_message())

    def event_filter(self, obj, event) -> bool:
        # In DOM-overlay mode, events are blocked inside the page by the overlay element.
        # Keep this hook for backward compatibility; don't block at Qt layer.
        _ = obj
        _ = event
        return False

