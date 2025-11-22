"""StyleSheet差分最適化パッチ

Qtの QWidget.setStyleSheet をモンキーパッチして以下を実現:
- 同一文字列の再適用をスキップ (再描画抑制)
- 適用/スキップ回数のカウンタ収集

注意:
- パッチは一度のみ適用 (idempotent)
- 個別ウィジェットに _last_style_sheet_cache 属性を付与
- 失敗は致命的でなく運用継続

取得可能情報:
get_style_counters() -> {"applied": int, "skipped": int}
reset_style_counters() でトグル前にリセットし、トグル後に取得で1回分のコスト計測

今後の拡張候補:
- ハッシュ化による巨大文字列比較の高速化 (len>500閾値導入)
- setPalette など他APIの差分適用
"""
from __future__ import annotations

from typing import Dict, Optional

try:
    from PySide6.QtWidgets import QWidget  # type: ignore
except Exception:  # pragma: no cover
    QWidget = None  # type: ignore

_original_setStyleSheet = None  # type: ignore
_original_qapp_setStyleSheet = None  # type: ignore
_applied: int = 0
_skipped: int = 0
# クラス別適用統計
_class_counts: Dict[str, int] = {}
_class_bytes: Dict[str, int] = {}


def apply_style_patch() -> None:
    """QWidget / QApplication の setStyleSheet を差分最適化版に置き換える (一度きり)"""
    global _original_setStyleSheet, _original_qapp_setStyleSheet

    # QWidget 部分
    if QWidget is not None and _original_setStyleSheet is None:
        _original_setStyleSheet = QWidget.setStyleSheet

        def _patched_widget(self: QWidget, style: str) -> None:  # type: ignore
            global _applied, _skipped, _class_counts, _class_bytes
            prev = getattr(self, "_last_style_sheet_cache", None)
            if prev == style:
                _skipped += 1
                return
            # QPushButton用の簡易自動ラップ (解析エラー低減)
            try:
                from PySide6.QtWidgets import QPushButton  # type: ignore
            except Exception:
                QPushButton = None  # type: ignore
            if QPushButton is not None and isinstance(self, QPushButton):
                # 既にセレクタを含まない単純プロパティ列の場合はラップ
                if style and '{' not in style and 'QPushButton' not in style:
                    cleaned = style.strip()
                    # 末尾に '}' が無い場合は単純プロパティ列とみなし包む
                    style = f"QPushButton {{ {cleaned} }}"
            _applied += 1
            cls_name = self.__class__.__name__
            _class_counts[cls_name] = _class_counts.get(cls_name, 0) + 1
            _class_bytes[cls_name] = _class_bytes.get(cls_name, 0) + len(style or "")
            setattr(self, "_last_style_sheet_cache", style)
            _original_setStyleSheet(self, style)  # type: ignore

        QWidget.setStyleSheet = _patched_widget  # type: ignore

    # QApplication 部分
    try:
        from PySide6.QtWidgets import QApplication  # type: ignore
    except Exception:  # pragma: no cover
        QApplication = None  # type: ignore

    if QApplication is not None and _original_qapp_setStyleSheet is None:
        _original_qapp_setStyleSheet = QApplication.setStyleSheet

        def _patched_app(self: QApplication, style: str) -> None:  # type: ignore
            global _applied, _skipped
            prev = getattr(self, "_last_app_style_sheet_cache", None)
            if prev == style:
                _skipped += 1
                return
            _applied += 1
            setattr(self, "_last_app_style_sheet_cache", style)
            _original_qapp_setStyleSheet(self, style)  # type: ignore

        QApplication.setStyleSheet = _patched_app  # type: ignore


def reset_style_counters() -> None:
    """適用/スキップカウンタをリセット (クラス別統計も初期化)"""
    global _applied, _skipped, _class_counts, _class_bytes
    _applied = 0
    _skipped = 0
    _class_counts = {}
    _class_bytes = {}


def get_style_counters() -> Dict[str, int]:
    """現在のカウンタ値を取得"""
    return {"applied": _applied, "skipped": _skipped}


from typing import Any

def get_style_class_stats(top_n: int = 8) -> Dict[str, Any]:
    """クラス別スタイル適用統計を取得

    Returns:
        {
            "classes": {
                className: {"count": int, "bytes": int}
            },
            "top": [ (className, count, bytes) ]  # 降順上位N
        }
    """
    # ソート
    items = [(k, _class_counts.get(k, 0), _class_bytes.get(k, 0)) for k in _class_counts.keys()]
    items.sort(key=lambda x: x[1], reverse=True)
    top = items[:top_n]
    classes = {k: {"count": c, "bytes": b} for k, c, b in items}
    return {"classes": classes, "top": top}


def is_patch_active() -> bool:
    """パッチが有効かどうかを判定"""
    return _original_setStyleSheet is not None

__all__ = [
    "apply_style_patch",
    "reset_style_counters",
    "get_style_counters",
    "get_style_class_stats",
    "is_patch_active",
]
