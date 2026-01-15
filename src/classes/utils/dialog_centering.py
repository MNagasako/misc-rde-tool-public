from __future__ import annotations

import os
from typing import Optional


def install_dialog_centering(*, enabled: bool = True, force: bool = False) -> bool:
    """アプリ全体のポップアップダイアログを親ウィンドウ中央へ寄せる。

    - QMessageBox / QDialog / QProgressDialog 等の "一瞬ズレて出る" 問題の対策。
    - 既存コードの個別センタリングとも共存可能。

    Returns:
        True if installed (or already installed).
    """

    if not enabled:
        return False

    # pytest 実行中は、アプリ全体 eventFilter が teardown 中の QWidget に触れて
    # Qt が不安定化するケースがあるため、既定ではインストールしない。
    if os.environ.get("PYTEST_CURRENT_TEST") and not force:
        return False

    try:
        from qt_compat.widgets import QApplication

        app = QApplication.instance()
        if app is None:
            return False

        existing = getattr(app, "_rde_dialog_centering_filter", None)
        if existing is not None:
            return True

        from qt_compat.core import QObject

        class _DialogCenteringFilter(QObject):
            def eventFilter(self, obj, event):  # noqa: N802 (Qt API)
                try:
                    from qt_compat.core import QTimer
                    from qt_compat.widgets import QApplication, QDialog, QWidget

                    if not isinstance(obj, QWidget):
                        return False
                    if not obj.isWindow():
                        return False

                    et = event.type()
                    if et not in (event.Type.Polish, event.Type.Show, event.Type.ParentChange):
                        return False

                    # 明示的に無効化したいダイアログ向け
                    try:
                        if obj.property("_rde_disable_auto_center") is True:
                            return False
                    except Exception:
                        pass

                    # QDialog系に限定（普通のトップレベルウィンドウは対象外）
                    try:
                        if not isinstance(obj, QDialog):
                            return False
                    except Exception:
                        return False

                    # 再入防止（Show/WinIdChange等で多重に呼ばれる）
                    try:
                        if obj.property("_rde_dialog_centering") is True:
                            return False
                        obj.setProperty("_rde_dialog_centering", True)
                    except Exception:
                        pass

                    def _center_now() -> None:
                        try:
                            from qt_compat.widgets import QApplication

                            anchor = _resolve_anchor(obj)
                            if anchor is not None:
                                _center_on_parent(obj, anchor)
                            else:
                                _center_on_screen(obj)
                        finally:
                            try:
                                obj.setProperty("_rde_dialog_centering", False)
                            except Exception:
                                pass

                    # レイアウト確定後に寄せる
                    try:
                        QTimer.singleShot(0, _center_now)
                    except Exception:
                        _center_now()
                except Exception:
                    return False
                return False

        flt = _DialogCenteringFilter(app)
        try:
            app.installEventFilter(flt)
        except Exception:
            return False

        setattr(app, "_rde_dialog_centering_filter", flt)
        return True
    except Exception:
        return False


def _resolve_anchor(dialog) -> Optional[object]:
    """親中央寄せの基準となるウィンドウを解決する。"""

    try:
        from qt_compat.widgets import QApplication, QWidget

        anchor = None
        try:
            anchor = dialog.parentWidget()
        except Exception:
            anchor = None

        # parentWidget が無い場合、parent が QWidget のケースも拾う
        if anchor is None:
            try:
                parent = dialog.parent()
                anchor = parent if isinstance(parent, QWidget) else None
            except Exception:
                anchor = None

        if anchor is not None:
            try:
                if anchor.isWindow():
                    return anchor
            except Exception:
                pass

        # アクティブウィンドウをフォールバック
        try:
            aw = QApplication.activeWindow()
            if aw is not None and aw is not dialog:
                return aw
        except Exception:
            pass

        return None
    except Exception:
        return None


def _center_on_parent(widget, parent) -> None:
    try:
        if widget is None or parent is None:
            return
        parent_geo = None
        try:
            parent_geo = parent.frameGeometry()
        except Exception:
            parent_geo = None
        if parent_geo is None:
            return
        fg = widget.frameGeometry()
        fg.moveCenter(parent_geo.center())
        widget.move(fg.topLeft())
    except Exception:
        return


def _center_on_screen(widget) -> None:
    try:
        from qt_compat.widgets import QApplication

        screen = None
        try:
            screen = widget.screen()
        except Exception:
            screen = None
        if screen is None:
            try:
                screen = QApplication.primaryScreen()
            except Exception:
                screen = None
        if screen is None:
            return

        geo = screen.availableGeometry()
        fg = widget.frameGeometry()
        fg.moveCenter(geo.center())
        widget.move(fg.topLeft())
    except Exception:
        return
