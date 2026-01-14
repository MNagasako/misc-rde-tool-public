from __future__ import annotations

from qt_compat.core import Qt
from qt_compat.core import QEvent
from qt_compat.gui import QBrush, QPainter, QPainterPath, QPen
from qt_compat.widgets import QStyledItemDelegate

from classes.theme import ThemeKey, get_qcolor


class ThemedCheckboxDelegate(QStyledItemDelegate):
    """ItemView のチェック表示をテーマ準拠で描画するデリゲート。

    目的:
    - 未チェック時: 背景透過 + ボーダーをはっきり
    - チェック時: 背景色 + チェックマーク色をテーマで制御

    NOTE: QSS だとチェックマーク色制御が難しいため、デリゲート描画で対応する。
    """

    @staticmethod
    def _normalize_check_state(value) -> int | None:
        if value is None:
            return None
        # PySide6 では Qt.CheckState が Python の enum 的に扱われ、int() が効かない場合がある。
        try:
            # type: ignore[attr-defined]
            return int(value.value)
        except Exception:
            pass
        try:
            return int(value)
        except Exception:
            return None

    def paint(self, painter: QPainter, option, index) -> None:  # type: ignore[override]
        # チェック列以外は標準描画
        check_state = index.data(Qt.CheckStateRole)
        if check_state is None:
            return super().paint(painter, option, index)

        painter.save()
        try:
            # 背景（選択/交互行）
            try:
                is_selected = bool(option.state & option.State_Selected)
            except Exception:
                is_selected = False

            # Alternate 判定は環境差があるためベストエフォート
            is_alternate = False
            try:
                if hasattr(option, "features") and hasattr(option, "Alternate"):
                    is_alternate = bool(option.features & option.Alternate)
            except Exception:
                is_alternate = False

            if is_selected:
                bg = get_qcolor(ThemeKey.BUTTON_PRIMARY_BACKGROUND)
            elif is_alternate:
                bg = get_qcolor(ThemeKey.PANEL_BACKGROUND)
            else:
                bg = get_qcolor(ThemeKey.INPUT_BACKGROUND)

            painter.fillRect(option.rect, QBrush(bg))

            # チェックボックス領域（中央寄せ）
            rect = option.rect
            size = int(min(16, rect.width() - 6, rect.height() - 6))
            if size < 10:
                size = int(min(12, rect.width() - 4, rect.height() - 4))
            if size < 8:
                return

            x = rect.x() + int((rect.width() - size) / 2)
            y = rect.y() + int((rect.height() - size) / 2)

            # PySide6 の QRect を直接 import せずに生成（互換層考慮）
            try:
                from qt_compat.core import QRect

                cb_rect = QRect(x, y, size, size)
            except Exception:
                cb_rect = rect

            border_color = get_qcolor(ThemeKey.BORDER_DEFAULT)
            checked_bg = get_qcolor(ThemeKey.BUTTON_PRIMARY_BACKGROUND)
            check_color = get_qcolor(ThemeKey.BUTTON_PRIMARY_TEXT)

            # チェック状態判定（PySide6 enum / int 両対応）
            normalized = self._normalize_check_state(check_state)
            checked = self._normalize_check_state(getattr(Qt, "Checked", None))
            if checked is None:
                # Qt の Checked は通常 2
                checked = 2
            is_checked = normalized == checked

            painter.setRenderHint(QPainter.Antialiasing, True)

            pen = QPen(border_color)
            pen.setWidth(1)
            painter.setPen(pen)

            if is_checked:
                painter.setBrush(QBrush(checked_bg))
            else:
                painter.setBrush(Qt.NoBrush)

            try:
                painter.drawRoundedRect(cb_rect, 3, 3)
            except Exception:
                painter.drawRect(cb_rect)

            if is_checked:
                # チェックマークを描画
                path = QPainterPath()
                left = cb_rect.left()
                top = cb_rect.top()
                w = cb_rect.width()
                h = cb_rect.height()

                path.moveTo(left + w * 0.22, top + h * 0.55)
                path.lineTo(left + w * 0.42, top + h * 0.74)
                path.lineTo(left + w * 0.78, top + h * 0.30)

                check_pen = QPen(check_color)
                check_pen.setWidth(max(2, int(size / 8)))
                check_pen.setCapStyle(Qt.RoundCap)
                check_pen.setJoinStyle(Qt.RoundJoin)
                painter.setPen(check_pen)
                painter.drawPath(path)

        finally:
            painter.restore()

    def editorEvent(self, event, model, option, index) -> bool:  # type: ignore[override]
        """チェック列の操作性を補強する。

        QSS/カスタム描画時に、セルクリックでチェックが切り替わらない環境があるため、
        ここで明示的に CheckStateRole をトグルする。
        """

        try:
            # チェック列以外は標準に委譲
            if index.data(Qt.CheckStateRole) is None:
                return super().editorEvent(event, model, option, index)

            flags = index.flags() if hasattr(index, "flags") else None
            if flags is not None:
                if not bool(flags & Qt.ItemIsEnabled) or not bool(flags & Qt.ItemIsUserCheckable):
                    return False

            et = event.type() if event is not None and hasattr(event, "type") else None

            # マウスクリックでトグル
            if et in (QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick):
                try:
                    if hasattr(event, "button") and event.button() != Qt.LeftButton:
                        return False
                except Exception:
                    pass

                current = index.data(Qt.CheckStateRole)
                normalized = self._normalize_check_state(current)
                checked = self._normalize_check_state(getattr(Qt, "Checked", None))
                unchecked = self._normalize_check_state(getattr(Qt, "Unchecked", None))
                if checked is None:
                    checked = 2
                if unchecked is None:
                    unchecked = 0

                new_value = Qt.Unchecked if normalized == checked else Qt.Checked
                return bool(model.setData(index, new_value, Qt.CheckStateRole))

            # Space キーでもトグル（テーブル側で eventFilter がないケース用）
            if et == QEvent.KeyPress:
                try:
                    if hasattr(event, "key") and event.key() != Qt.Key_Space:
                        return False
                except Exception:
                    return False

                current = index.data(Qt.CheckStateRole)
                normalized = self._normalize_check_state(current)
                checked = self._normalize_check_state(getattr(Qt, "Checked", None))
                if checked is None:
                    checked = 2
                new_value = Qt.Unchecked if normalized == checked else Qt.Checked
                return bool(model.setData(index, new_value, Qt.CheckStateRole))

            return super().editorEvent(event, model, option, index)
        except Exception:
            return super().editorEvent(event, model, option, index)
