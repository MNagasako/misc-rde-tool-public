import logging
from typing import Iterable, List, Tuple
import weakref

try:
    from qt_compat.widgets import QComboBox, QWidget
except Exception:  # pragma: no cover - Qt import guard
    QComboBox = None  # type: ignore
    QWidget = object  # type: ignore

logger = logging.getLogger("ThemePerf")
_LARGE_COMBO_CACHE: List[weakref.ReferenceType] = []  # weak refs to large combos

def classify_combo_size(count: int) -> str:
    if count >= 5000:
        return 'xl'
    if count >= 2000:
        return 'lg'
    if count >= 1000:
        return 'md'
    return 'sm'

def _deferred_restyle(combo, delay_ms: int = 75) -> None:
    """Deferred lightweight restyle using singleShot to avoid blocking styleApply.

    Re-applies an empty stylesheet to ensure global inheritance only; could be
    extended to apply a minimal per-combo style in the future.
    """
    try:
        from PySide6.QtCore import QTimer  # type: ignore
        QTimer.singleShot(delay_ms, lambda c=combo: _safe_minimal_combo_style(c))
    except Exception:
        _safe_minimal_combo_style(combo)

def _safe_minimal_combo_style(combo) -> None:
    try:
        combo.setStyleSheet("")
    except Exception:
        pass

def optimize_combo_boxes(root: QWidget, threshold: int = 500) -> None:
    """Optimize large QComboBox instances during theme refresh.

    This avoids expensive full restyling / relayout passes for very large
    combo boxes (thousands of entries) by:
      - Disabling updates during stylesheet changes
      - Clearing per-instance stylesheet (fallback to global stylesheet)
      - Enabling uniform item sizes for view to skip per-row size calc
      - Restoring current index without emitting signals

    Only combo boxes with item count >= threshold are processed.
    Safe no-op if Qt classes unavailable.
    """
    if QComboBox is None or root is None:
        return

    try:
        combos: Iterable[QComboBox] = root.findChildren(QComboBox)
    except Exception:
        return

    processed = 0
    for combo in combos:
        count = combo.count()
        if count < threshold:
            continue
        try:
            processed += 1
            combo.blockSignals(True)
            combo.setUpdatesEnabled(False)
            current_index = combo.currentIndex()

            # Rely only on global stylesheet to avoid per-instance heavy recalculation
            combo.setStyleSheet("")

            # Uniform item sizes reduces sizeHintForIndex cost
            try:
                view = combo.view()
                if hasattr(view, 'setUniformItemSizes'):
                    view.setUniformItemSizes(True)
            except Exception:
                pass

            # Limit max visible items to reduce popup sizing cost
            if count > 1000 and combo.maxVisibleItems() > 40:
                combo.setMaxVisibleItems(40)

            # Restore index silently
            if 0 <= current_index < combo.count():
                combo.setCurrentIndex(current_index)
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("optimize_combo_boxes: combo optimization skipped due to error: %s", e)
        finally:
            try:
                combo.setUpdatesEnabled(True)
                combo.blockSignals(False)
            except Exception:
                pass

    if processed:
        logger.debug("optimize_combo_boxes: processed %d large combo boxes (threshold=%d)", processed, threshold)

def optimize_global_large_combos(threshold: int = 500, deferred: bool = True) -> int:
    """Scan all widgets in the QApplication and optimize large QComboBox.

    Returns number of processed combo boxes. Safe no-op if QApplication/QComboBox
    unavailable. Intended for invocation directly after global stylesheet/palette
    application to mitigate repaint storms.
    """
    if QComboBox is None:
        return 0
    try:
        from PySide6.QtWidgets import QApplication  # type: ignore
    except Exception:
        return 0
    app = QApplication.instance()
    if app is None:
        return 0
    processed = 0
    size_classes: List[Tuple[str, int]] = []
    # Rebuild cache if empty (first run)
    global _LARGE_COMBO_CACHE
    if not _LARGE_COMBO_CACHE:
        try:
            for w in app.allWidgets():
                if isinstance(w, QComboBox) and w.count() >= threshold:
                    _LARGE_COMBO_CACHE.append(weakref.ref(w))
        except Exception:
            pass

    # Iterate cached combos; drop dead references
    alive_cache: List[weakref.ReferenceType] = []
    for ref in _LARGE_COMBO_CACHE:
        combo = ref()
        if combo is None:
            continue
        alive_cache.append(ref)
        try:
            count = combo.count()
            size_classes.append((classify_combo_size(count), count))
            combo.blockSignals(True)
            combo.setUpdatesEnabled(False)
            current_index = combo.currentIndex()
            # Immediate light style clear to remove per-instance heavy QSS
            combo.setStyleSheet("")
            try:
                view = combo.view()
                if hasattr(view, 'setUniformItemSizes'):
                    view.setUniformItemSizes(True)
            except Exception:
                pass
            if count > 1000 and combo.maxVisibleItems() > 40:
                combo.setMaxVisibleItems(40)
            if 0 <= current_index < combo.count():
                combo.setCurrentIndex(current_index)
            # Deferred restyle (non-blocking) if requested
            if deferred:
                _deferred_restyle(combo)
        except Exception as e:  # pragma: no cover
            logger.debug("optimize_global_large_combos: cached combo skipped due to %s", e)
        finally:
            try:
                combo.setUpdatesEnabled(True)
                combo.blockSignals(False)
            except Exception:
                pass
        processed += 1
    _LARGE_COMBO_CACHE = alive_cache
    if processed:
        # Aggregate size class counts
        class_counter = {}
        for cls, cnt in size_classes:
            class_counter[cls] = class_counter.get(cls, 0) + 1
        logger.debug(
            "optimize_global_large_combos: processed %d combos %s (threshold=%d, deferred=%s)",
            processed,
            class_counter,
            threshold,
            deferred,
        )
    return processed
