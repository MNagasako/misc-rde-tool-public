"""
テーマ管理 - ARIM RDE Tool v2.4.14

ライト/ダークテーマの切り替えとカラー取得を一元管理。
Singleton パターンで全UI要素から参照可能。
"""

from enum import Enum
from typing import Optional
import os
import weakref
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from .theme_keys import ThemeKey
from .light_theme import LightTheme
from .dark_theme import DarkTheme


class ThemeMode(Enum):
    """テーマモード列挙型 (AUTO廃止: v2.1.8)

    起動時に OS テーマを検出して初期モードを決定し、
    以後はユーザー操作で LIGHT/DARK をトグルする。
    """
    LIGHT = "light"
    DARK = "dark"


class ThemeManager(QObject):
    """テーマ管理クラス（Singleton）
    
    全UIコンポーネントから参照される色管理の中心。
    テーマ変更時にシグナルを発行してUI再描画をトリガー。
    
    使用例:
        >>> theme = ThemeManager.instance()
        >>> color = theme.get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)
        >>> theme.set_mode(ThemeMode.DARK)  # ダークモードに切り替え
    """
    
    # Singleton インスタンス
    _instance: Optional['ThemeManager'] = None
    
    # テーマ変更通知シグナル
    theme_changed = Signal(ThemeMode)  # 新しいテーマモードを通知
    
    def __new__(cls):
        """Singleton実装"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初期化（初回のみ実行）"""
        if self._initialized:
            return
        
        super().__init__()
        self._current_mode = ThemeMode.LIGHT  # デフォルトはライトモード
        self._initialized = True
        # グローバルQSSキャッシュ: {ThemeMode: str}
        self._global_style_cache = {}
        # 最後に適用したQSSのハッシュ
        self._last_style_hash = None
        # QTextEdit/QTextBrowser viewport へ直接スタイルを当てる仕組み
        self._text_area_viewport_styler = None
        self._text_area_viewport_targets = weakref.WeakSet()
        self._text_area_viewport_bootstrapped = False
        # QScrollArea viewport へ直接スタイルを当てる仕組み（未塗り領域の黒化対策）
        self._scroll_area_viewport_styler = None
        self._scroll_area_viewport_targets = weakref.WeakSet()
        self._scroll_area_viewport_bootstrapped = False
        # QComboBox(非editable) placeholder の互換モード適用
        self._combo_placeholder_compat_styler = None
        self._combo_placeholder_compat_bootstrapped = False
        self._qt_qcombobox_type = None

        # Native window frame (title bar) theming
        self._window_frame_styler = None
        self._window_frame_bootstrapped = False

    def _ensure_window_frame_styler(self, app: QApplication) -> None:
        """新規に表示されるトップレベルウィンドウ/ダイアログにもタイトルバーのテーマを適用する。"""
        if self._window_frame_styler is None:
            theme_manager = self

            class _WindowFrameStyler(QObject):
                def eventFilter(self, obj, event):  # type: ignore[override]
                    try:
                        from PySide6.QtWidgets import QWidget
                        if not isinstance(obj, QWidget):
                            return False
                        # Top-level only (dialogs/windows)
                        if not obj.isWindow():
                            return False

                        # Re-entrancy guard:
                        # apply_window_frame_theme() が winId()/style 更新を通じて WinIdChange/Show を再発火し、
                        # eventFilter が再入すると無限再帰→stack overflow になり得る。
                        try:
                            if obj.property("_rde_window_frame_theming") is True:
                                return False
                        except Exception:
                            pass

                        et = event.type()
                        if et in (
                            event.Type.Polish,
                            event.Type.Show,
                            event.Type.WinIdChange,
                            event.Type.ParentChange,
                        ):
                            from classes.theme.window_frame import apply_window_frame_theme
                            try:
                                obj.setProperty("_rde_window_frame_theming", True)
                            except Exception:
                                pass
                            try:
                                apply_window_frame_theme(obj, mode=theme_manager.get_mode())
                            finally:
                                try:
                                    obj.setProperty("_rde_window_frame_theming", False)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    return False

            self._window_frame_styler = _WindowFrameStyler(app)
            try:
                app.installEventFilter(self._window_frame_styler)
            except Exception:
                self._window_frame_styler = None
                return

        # 既存トップレベルにも初回だけ適用
        if not self._window_frame_bootstrapped:
            try:
                from classes.theme.window_frame import apply_window_frame_theme

                apply_window_frame_theme(None, mode=self.get_mode())
            except Exception:
                pass
            self._window_frame_bootstrapped = True

    def _apply_combo_placeholder_compat(self, widget: object) -> None:
        """非editable QComboBox の placeholder を確実にテーマ制御するための互換モード。

        QProxyStyle でのラベル描画差し替えは環境依存でクラッシュし得るため、
        placeholderText を持つ非editableコンボは editable + readOnly lineEdit に変換し、
        placeholderは lineEdit 側の描画（palette制御）に寄せる。
        """
        try:
            qcombobox_type = self._qt_qcombobox_type
            if qcombobox_type is None:
                from PySide6.QtWidgets import QComboBox as _QComboBox

                self._qt_qcombobox_type = _QComboBox
                qcombobox_type = _QComboBox

            if not isinstance(widget, qcombobox_type):
                return

            combo = widget
            if combo.isEditable():
                return
            if not combo.placeholderText():
                return

            # 二重適用防止
            try:
                if combo.property("rde_placeholder_compat") is True:
                    return
            except Exception:
                pass

            # NOTE:
            # setEditable(True) 等は内部でイベント（ParentChange/Showなど）を再発火し、
            # 本メソッドがイベントフィルタ経由で再入する場合がある。
            # 先にガードを立てて無限ループを防ぐ。
            try:
                combo.setProperty("rde_placeholder_compat", True)
            except Exception:
                pass

            combo.setEditable(True)
            combo.setInsertPolicy(qcombobox_type.InsertPolicy.NoInsert)
            le = combo.lineEdit()
            if le is not None:
                le.setReadOnly(True)
                le.setPlaceholderText(combo.placeholderText())
        except Exception:
            return

    def _ensure_combo_placeholder_compat_styler(self, app: QApplication) -> None:
        """新規生成されるQComboBoxにも互換モードを自動適用するイベントフィルタを導入。"""
        if self._combo_placeholder_compat_styler is None:
            theme_manager = self

            class _ComboPlaceholderCompatStyler(QObject):
                def eventFilter(self, obj, event):  # type: ignore[override]
                    try:
                        et = event.type()
                        if et in (event.Type.Show, event.Type.ParentChange):
                            theme_manager._apply_combo_placeholder_compat(obj)
                    except Exception:
                        pass
                    return False

            self._combo_placeholder_compat_styler = _ComboPlaceholderCompatStyler(app)
            try:
                app.installEventFilter(self._combo_placeholder_compat_styler)
            except Exception:
                self._combo_placeholder_compat_styler = None
                return

        # 互換モードはテーマに依存しないため、既存一括適用は初回のみ行う
        # ただしpytest環境では全ウィジェット走査が重く、タイムアウトの原因になり得るためスキップする。
        if not self._combo_placeholder_compat_bootstrapped:
            if os.environ.get("PYTEST_CURRENT_TEST"):
                self._combo_placeholder_compat_bootstrapped = True
                return
            try:
                for w in QApplication.allWidgets():
                    self._apply_combo_placeholder_compat(w)
            except Exception:
                pass
            self._combo_placeholder_compat_bootstrapped = True

    def _build_text_area_viewport_style_sheet(self) -> str:
        """QTextEdit/QTextBrowser の viewport に直接当てるQSSを生成。"""
        # NOTE:
        # - ::viewport / #qt_scrollarea_viewport セレクタは環境差で効かない/揺れる報告があるため、
        #   viewportウィジェット自身に styleSheet を設定する（最も確実）。
        return (
            "QWidget {"
            f" background-color: {self.get_color(ThemeKey.TEXT_AREA_BACKGROUND)};"
            f" color: {self.get_color(ThemeKey.INPUT_TEXT)};"
            f" border: {self.get_color(ThemeKey.INPUT_BORDER_WIDTH)} solid {self.get_color(ThemeKey.INPUT_BORDER)};"
            " border-radius: 4px;"
            " padding: 4px;"
            " }"
            " QWidget:disabled {"
            f" background-color: {self.get_color(ThemeKey.TEXT_AREA_BACKGROUND_DISABLED)};"
            f" color: {self.get_color(ThemeKey.TEXT_AREA_TEXT_DISABLED)};"
            f" border: 1px solid {self.get_color(ThemeKey.INPUT_BORDER_DISABLED)};"
            " }"
        )

    def _build_scroll_area_viewport_style_sheet(self) -> str:
        """QScrollArea の viewport へ直接当てるQSSを生成。

        NOTE:
        - QScrollArea は内部に viewport(QWidget) を持ち、そこが未塗り/透明のままだと
          Windows環境で黒い矩形が見えるケースがある。
        - セレクタ (::viewport 等) の揺れを避け、viewportウィジェット自身へ設定する。
        """

        return (
            "QWidget {"
            f" background-color: {self.get_color(ThemeKey.WINDOW_BACKGROUND)};"
            f" color: {self.get_color(ThemeKey.WINDOW_FOREGROUND)};"
            " }"
        )

    def _apply_scroll_area_viewport_style(self, widget: object, *, only_when_visible: bool = False) -> None:
        """対象ウィジェットが QScrollArea なら viewport へ直接スタイルを当てる。"""
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QScrollArea

            if not isinstance(widget, QScrollArea):
                return

            # テーマ切替時の全走査で、過去のテスト/ウィジェットで生成された
            # 非表示ScrollAreaまで大量に再スタイルするとpytestがタイムアウトし得る。
            # 非表示のものは Show イベントで拾えるため、必要に応じて可視に限定する。
            if only_when_visible:
                try:
                    if not widget.isVisible():
                        return
                except Exception:
                    pass

            try:
                self._scroll_area_viewport_targets.add(widget)
            except Exception:
                pass

            if not hasattr(widget, "viewport"):
                return
            vp = widget.viewport()
            try:
                widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                vp.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            except Exception:
                pass

            qss = self._build_scroll_area_viewport_style_sheet()
            try:
                if getattr(vp, "styleSheet", None) and vp.styleSheet() == qss:
                    return
            except Exception:
                pass
            vp.setStyleSheet(qss)
        except Exception:
            return

    def _ensure_scroll_area_viewport_styler(self, app: QApplication) -> None:
        """新規生成される QScrollArea にも自動適用するイベントフィルタを導入。"""
        if self._scroll_area_viewport_styler is None:
            theme_manager = self

            class _ScrollAreaViewportStyler(QObject):
                def eventFilter(self, obj, event):  # type: ignore[override]
                    try:
                        et = event.type()
                        if et in (event.Type.Polish, event.Type.Show, event.Type.ParentChange):
                            theme_manager._apply_scroll_area_viewport_style(obj)
                    except Exception:
                        pass
                    return False

            self._scroll_area_viewport_styler = _ScrollAreaViewportStyler(app)
            try:
                app.installEventFilter(self._scroll_area_viewport_styler)
            except Exception:
                self._scroll_area_viewport_styler = None
                return

        if not self._scroll_area_viewport_bootstrapped:
            try:
                for w in QApplication.allWidgets():
                    self._apply_scroll_area_viewport_style(w, only_when_visible=True)
            except Exception:
                pass
            self._scroll_area_viewport_bootstrapped = True
        else:
            try:
                for w in list(self._scroll_area_viewport_targets):
                    self._apply_scroll_area_viewport_style(w, only_when_visible=True)
            except Exception:
                pass

    def _apply_text_area_viewport_style(self, widget: object) -> None:
        """対象ウィジェットがテキストエリアなら viewport へ直接スタイルを当てる。"""
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QTextEdit, QTextBrowser, QPlainTextEdit

            if not isinstance(widget, (QTextEdit, QTextBrowser, QPlainTextEdit)):
                return

            # 既存追跡（テーマ切替時の再適用を全走査せずに実現）
            try:
                self._text_area_viewport_targets.add(widget)
            except Exception:
                pass

            if not hasattr(widget, "viewport"):
                return

            vp = widget.viewport()
            try:
                widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                vp.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            except Exception:
                pass

            qss = self._build_text_area_viewport_style_sheet()
            # 同一QSSは再適用しない（無駄なpolishを避ける）
            try:
                if getattr(vp, "styleSheet", None) and vp.styleSheet() == qss:
                    return
            except Exception:
                pass
            vp.setStyleSheet(qss)
        except Exception:
            # 失敗してもテーマ適用全体は継続
            return

    def _ensure_text_area_viewport_styler(self, app: QApplication) -> None:
        """新規生成されるテキストエリアにも自動適用するイベントフィルタを導入。"""
        if self._text_area_viewport_styler is None:
            theme_manager = self

            class _TextAreaViewportStyler(QObject):
                def eventFilter(self, obj, event):  # type: ignore[override]
                    try:
                        et = event.type()
                        # Polish/Show/ParentChange あたりで拾う（取りこぼしを減らす）
                        if et in (event.Type.Polish, event.Type.Show, event.Type.ParentChange):
                            theme_manager._apply_text_area_viewport_style(obj)
                    except Exception:
                        pass
                    return False

            self._text_area_viewport_styler = _TextAreaViewportStyler(app)
            try:
                app.installEventFilter(self._text_area_viewport_styler)
            except Exception:
                self._text_area_viewport_styler = None
                return

        # 既存の拾い上げは初回のみ allWidgets で行い、以降は追跡集合のみを再適用
        if not self._text_area_viewport_bootstrapped:
            try:
                for w in QApplication.allWidgets():
                    self._apply_text_area_viewport_style(w)
            except Exception:
                pass
            self._text_area_viewport_bootstrapped = True
        else:
            try:
                for w in list(self._text_area_viewport_targets):
                    self._apply_text_area_viewport_style(w)
            except Exception:
                pass
    
    @classmethod
    def instance(cls) -> 'ThemeManager':
        """Singletonインスタンス取得
        
        Returns:
            ThemeManagerインスタンス
        """
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance
    
    def get_color(self, key: ThemeKey) -> str:
        """指定されたキーの色を取得
        
        現在のテーマモードに応じて適切な色を返す。
        
        Args:
            key: テーマキー（ThemeKey列挙型）
            
        Returns:
            色文字列（#RRGGBB または rgba(...)）
            
        Raises:
            KeyError: キーが存在しない場合
            
        使用例:
            >>> theme = ThemeManager.instance()
            >>> bg_color = theme.get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)
            >>> text_color = theme.get_color(ThemeKey.TEXT_PRIMARY)
        """
        theme_class = self._get_current_theme_class()
        return theme_class.get_color(key)
    
    def get_mode(self) -> ThemeMode:
        """現在のテーマモードを取得
        
        Returns:
            現在のテーマモード
        """
        return self._current_mode
    
    def set_mode(self, mode: ThemeMode) -> None:
        """テーマモードを設定
        
        モードが変更された場合、theme_changedシグナルを発行。
        同一モードでも再適用が要求されるケース(OS変更同期など)は再適用処理のみを実行。
        
        差分最適化:
        - setStyleSheet同一文字列再適用をスキップ (style_patch)
        - トグル毎の適用/スキップ回数をログ出力し冗長度を計測
        - 各処理フェーズの所要時間を計測し遅延箇所を特定
        
        Args:
            mode: 新しいテーマモード
            
        使用例:
            >>> theme = ThemeManager.instance()
            >>> theme.set_mode(ThemeMode.DARK)
        """
        import os
        import time
        total_start = time.perf_counter_ns()

        # pytest 実行時は、グローバルQSS適用(app.setStyleSheet)やタイトルバー再適用が
        # 既存ウィジェット数に比例して高コスト/不安定になり、timeoutを誘発し得る。
        # テストでは個別ウィジェットのstyleSheet/palette反映が主目的のため、
        # それらは維持しつつ重い処理をスキップする。
        is_pytest_run = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        
        mode_changed = mode != self._current_mode
        if mode_changed:
            old_mode = self._current_mode
            self._current_mode = mode
            self.theme_changed.emit(mode)
            print(f"[ThemeManager] Theme changed: {old_mode.value} → {mode.value}")
        else:
            print(f"[ThemeManager] Theme reapply (same mode: {mode.value})")

        # Qt側の描画キャッシュをクリア（テーマ切替後に旧配色が残るのを防ぐ）
        try:
            from PySide6.QtGui import QPixmapCache

            QPixmapCache.clear()
        except Exception:
            pass

        # 差分スタイルパッチの準備 (失敗しても継続)
        try:
            from classes.utils.style_patch import apply_style_patch, reset_style_counters, get_style_counters
            apply_style_patch()
            reset_style_counters()
        except Exception as patch_err:  # pragma: no cover
            print(f"[ThemeManager] style patch init skipped: {patch_err}")

        app = QApplication.instance()
        if app is not None:
            try:
                # === updatesEnabled バッチ無効化開始 ===
                top_levels = []
                if not is_pytest_run:
                    try:
                        top_levels = [w for w in QApplication.topLevelWidgets() if hasattr(w, "setUpdatesEnabled")]
                    except Exception:
                        top_levels = []
                    for w in top_levels:
                        try:
                            w.setUpdatesEnabled(False)
                        except Exception:
                            pass
                # グローバルスタイル適用
                # --- Style Phase Micro Profiling ---
                cached = False
                apply_skipped = False
                gen_elapsed = 0.0
                apply_elapsed = 0.0
                style_total_elapsed = 0.0
                if not is_pytest_run:
                    from .global_styles import get_global_base_style  # type: ignore
                    import hashlib

                    style_phase_start = time.perf_counter_ns()
                    # (1) Generation (or cache retrieval)
                    gen_start = time.perf_counter_ns()
                    qss = self._global_style_cache.get(self._current_mode)
                    if qss is None:
                        qss = get_global_base_style()
                        self._global_style_cache[self._current_mode] = qss
                        gen_elapsed = (time.perf_counter_ns() - gen_start) / 1_000_000
                        print(
                            f"[ThemeManager] global QSS generated ({gen_elapsed:.2f}ms, mode={self._current_mode.value}, length={len(qss)})"
                        )
                    else:
                        cached = True
                        gen_elapsed = (time.perf_counter_ns() - gen_start) / 1_000_000
                        print(f"[ThemeManager] global QSS cache hit (mode={self._current_mode.value}, length={len(qss)})")

                    # (2) Hash comparison + (conditional) application
                    apply_start = time.perf_counter_ns()
                    style_hash = hashlib.sha256(qss.encode("utf-8")).hexdigest()
                    if self._last_style_hash == style_hash:
                        apply_skipped = True
                        print("[ThemeManager] global QSS unchanged - apply skipped (hash match)")
                    else:
                        app.setStyleSheet(qss)
                        self._last_style_hash = style_hash
                    apply_elapsed = (time.perf_counter_ns() - apply_start) / 1_000_000

                    # (3) (Deferred) Repaint/layout cost will be measured after updates re-enable
                    # Store partials for later summary
                    style_total_elapsed = (time.perf_counter_ns() - style_phase_start) / 1_000_000
                
                # パレット適用
                palette_start = time.perf_counter_ns()
                self.apply_palette()
                palette_elapsed = (time.perf_counter_ns() - palette_start) / 1_000_000

                # ネイティブタイトルバー配色もテーマに追従（ダイアログ/別ウィンドウ含む）
                try:
                    self._ensure_window_frame_styler(app)
                except Exception:
                    pass

                # QTextEdit/QTextBrowser の viewport へ直接スタイル適用（環境差対策）
                try:
                    self._ensure_text_area_viewport_styler(app)
                except Exception:
                    pass

                # QScrollArea の viewport へ直接スタイル適用（未塗り領域の黒化対策）
                try:
                    self._ensure_scroll_area_viewport_styler(app)
                except Exception:
                    pass

                # QComboBox(非editable) placeholder の環境差対策（互換モード）
                try:
                    self._ensure_combo_placeholder_compat_styler(app)
                except Exception:
                    pass
                
                # 大量ComboBox最適化
                combo_elapsed = 0.0
                if not is_pytest_run:
                    try:
                        combo_start = time.perf_counter_ns()
                        from classes.utils.theme_perf_util import optimize_global_large_combos

                        processed = optimize_global_large_combos(threshold=500, deferred=True)
                        combo_elapsed = (time.perf_counter_ns() - combo_start) / 1_000_000
                        if processed:
                            print(f"[ThemeManager] optimized {processed} large combo boxes ({combo_elapsed:.2f}ms)")
                    except Exception as opt_e:  # pragma: no cover
                        print(f"[ThemeManager] combo optimization skipped: {opt_e}")
                
                # 処理時間サマリー
                total_elapsed = (time.perf_counter_ns() - total_start) / 1_000_000
                # 追加メタ情報: cached / skipped / disabledWidgets を出力
                meta = []
                if cached:
                    meta.append("cached")
                if apply_skipped:
                    meta.append("skip-set")
                if top_levels:
                    meta.append(f"updOff={len(top_levels)}")
                meta_str = (" [" + ",".join(meta) + "]") if meta else ""
                # Repaint/layout elapsed measured after enabling updates (below). Placeholder=0 now.
                repaint_elapsed = 0.0
                print(
                    f"[ThemeManager] Timing: styleGen={gen_elapsed:.2f}ms styleApply={apply_elapsed:.2f}ms "
                    f"styleTotal={style_total_elapsed:.2f}ms repaint={repaint_elapsed:.2f}ms palette={palette_elapsed:.2f}ms "
                    f"combo={combo_elapsed:.2f}ms total={total_elapsed:.2f}ms{meta_str}"
                )
                
            except Exception as e:
                print(f"[ThemeManager] apply palette failed: {e}")
            finally:
                # === updatesEnabled バッチ再有効化 ===
                repaint_start = time.perf_counter_ns()
                for w in top_levels:
                    try:
                        w.setUpdatesEnabled(True)
                    except Exception:
                        pass
                # Process pending events.
                # NOTE: On Windows + pytest, native message pumping (processEvents/sendPostedEvents)
                # can still trigger sporadic SEH crashes in long runs. For tests we avoid it.
                try:
                    import os

                    if not os.environ.get("PYTEST_CURRENT_TEST"):
                        app.processEvents()
                except Exception:
                    pass

                # タイトルバーの適用はネイティブAPIを触るため、pytest実行時は省略する。
                try:
                    import os

                    if not os.environ.get("PYTEST_CURRENT_TEST"):
                        from classes.theme.window_frame import apply_window_frame_theme

                        apply_window_frame_theme(None, mode=self.get_mode())
                except Exception:
                    pass
                # Optional targeted update
                if not is_pytest_run:
                    for w in top_levels:
                        try:
                            if hasattr(w, "update"):
                                w.update()
                        except Exception:
                            pass
                repaint_elapsed = (time.perf_counter_ns() - repaint_start) / 1_000_000
                # Emit refined timing summary (micro-profile + repaint)
                print(f"[ThemeManager] Timing(refined): repaint={repaint_elapsed:.2f}ms (topLevels={len(top_levels)})")
                # カウンタ取得とログ
                try:
                    from classes.utils.style_patch import get_style_counters, get_style_class_stats
                    counters = get_style_counters()
                    applied = counters.get("applied", 0)
                    skipped = counters.get("skipped", 0)
                    total = applied + skipped
                    redundancy = (skipped / total * 100.0) if total else 0.0
                    print(f"[ThemeManager] style diff stats: applied={applied} skipped={skipped} redundancy={redundancy:.1f}%")
                    class_stats = get_style_class_stats(top_n=5)
                    top = class_stats.get("top", [])
                    if top:
                        summary = ", ".join([f"{name}:{cnt}" for name, cnt, _b in top])
                        print(f"[ThemeManager] style class top5: {summary}")
                except Exception as stat_err:  # pragma: no cover
                    print(f"[ThemeManager] style stats skipped: {stat_err}")
                # =============================
                # Widget 階層メトリクス (スパイク分析用)
                # style適用が高コストだった場合のみ計測しオーバーヘッドを最小化
                # =============================
                try:
                    spike_threshold_ms = 800.0  # total elapsed の暫定閾値
                    if apply_elapsed > spike_threshold_ms or repaint_elapsed > spike_threshold_ms:
                        import time as _t
                        hier_start = _t.perf_counter_ns()
                        from PySide6.QtWidgets import QWidget
                        # BFSで深さと型頻度を収集
                        type_counts = {}
                        depth_counts = {}
                        max_depth = 0
                        heavy_subtrees = []  # (className, subtreeSize)
                        for tl in top_levels:
                            if not isinstance(tl, QWidget):
                                continue
                            queue = [(tl, 0)]
                            subtree_nodes = 0
                            while queue:
                                node, depth = queue.pop(0)
                                subtree_nodes += 1
                                cname = node.__class__.__name__
                                type_counts[cname] = type_counts.get(cname, 0) + 1
                                depth_counts[depth] = depth_counts.get(depth, 0) + 1
                                if depth > max_depth:
                                    max_depth = depth
                                for ch in node.children():
                                    if isinstance(ch, QWidget):
                                        queue.append((ch, depth + 1))
                            heavy_subtrees.append((tl.__class__.__name__, subtree_nodes))
                        # 上位型/深さ/重いサブツリー出力
                        top_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:5]
                        top_depths = sorted(depth_counts.items(), key=lambda x: x[0])[:6]
                        heavy_sorted = sorted(heavy_subtrees, key=lambda x: x[1], reverse=True)[:3]
                        hier_elapsed = (_t.perf_counter_ns() - hier_start) / 1_000_000
                        if top_types:
                            type_summary = ", ".join([f"{t}:{c}" for t, c in top_types])
                            print(f"[ThemeManager] hierarchy types top5: {type_summary}")
                        if heavy_sorted:
                            heavy_summary = ", ".join([f"{t}:{sz}" for t, sz in heavy_sorted])
                            print(f"[ThemeManager] hierarchy heavy subtrees top3: {heavy_summary}")
                        depth_summary = ", ".join([f"d{d}:{c}" for d, c in top_depths])
                        print(f"[ThemeManager] hierarchy depth dist: {depth_summary} maxDepth={max_depth} nodes={sum(type_counts.values())} ({hier_elapsed:.2f}ms)")
                except Exception as hier_err:  # pragma: no cover
                    print(f"[ThemeManager] hierarchy metrics skipped: {hier_err}")
    
    def toggle_mode(self) -> ThemeMode:
        """ライト/ダークモードをトグル切り替え
        
        現在がライトならダーク、ダークならライトに切り替える。
        AUTOモードの場合は何もしない。
        
        Returns:
            切り替え後のテーマモード
        """
        if self._current_mode == ThemeMode.LIGHT:
            self.set_mode(ThemeMode.DARK)
        elif self._current_mode == ThemeMode.DARK:
            self.set_mode(ThemeMode.LIGHT)
        # AUTOモードの場合は何もしない
        
        return self._current_mode
    
    def cycle_mode(self) -> ThemeMode:
        """互換用: 2状態トグル (AUTO廃止後)

        旧コードが cycle_mode() を呼ぶケースを維持するためのラッパ。
        """
        return self.toggle_mode()
    
    def detect_system_theme(self) -> ThemeMode:
        """OS設定から現在のテーマを検出
        
        Returns:
            LIGHT または DARK
        """
        app = QApplication.instance()
        if app is None:
            return ThemeMode.LIGHT  # フォールバック
        
        palette = app.palette()
        # 背景色の輝度で判定
        bg_color = palette.color(QPalette.ColorRole.Window)
        luminance = (0.299 * bg_color.red() + 
                     0.587 * bg_color.green() + 
                     0.114 * bg_color.blue())
        
        # 輝度が128未満ならダークモード
        return ThemeMode.DARK if luminance < 128 else ThemeMode.LIGHT
    
    def get_all_colors(self) -> dict[ThemeKey, str]:
        """現在のテーマの全色定義を取得
        
        デバッグ用途。
        
        Returns:
            {ThemeKey: 色文字列} の辞書
        """
        theme_class = self._get_current_theme_class()
        return theme_class.get_all_colors()
    
    def validate_theme(self) -> tuple[bool, list[ThemeKey]]:
        """現在のテーマの完全性をチェック
        
        Returns:
            (完全かどうか, 未定義のキーリスト)
        """
        theme_class = self._get_current_theme_class()
        return theme_class.validate_completeness()
    
    def _get_current_theme_class(self):
        """現在モードに対応するテーマクラスを取得"""
        if self._current_mode == ThemeMode.DARK:
            return DarkTheme
        return LightTheme
    
    # ========================================
    # 便利メソッド：よく使う色へのショートカット
    # ========================================
    
    def get_primary_color(self) -> str:
        """プライマリカラー（ボタン背景等）を取得"""
        return self.get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)
    
    def get_text_color(self) -> str:
        """通常テキスト色を取得"""
        return self.get_color(ThemeKey.TEXT_PRIMARY)
    
    def get_background_color(self) -> str:
        """メイン背景色を取得"""
        return self.get_color(ThemeKey.WINDOW_BACKGROUND)
    
    def get_error_color(self) -> str:
        """エラー表示色を取得"""
        return self.get_color(ThemeKey.TEXT_ERROR)
    
    def get_success_color(self) -> str:
        """成功表示色を取得"""
        return self.get_color(ThemeKey.TEXT_SUCCESS)
    
    def get_warning_color(self) -> str:
        """警告表示色を取得"""
        return self.get_color(ThemeKey.TEXT_WARNING)

    # ========================================
    # パレット強制適用（OSテーマに依存しない基底色の統一）
    # ========================================
    def apply_palette(self) -> None:
        """QApplication パレットへ現在テーマの主要色を差分適用

        変更された ColorRole のみ setColor を実行し、不要な再描画を抑制。
        """
        app = QApplication.instance()
        if app is None:
            return
        pal = app.palette()

        # NOTE: 直接の QColor() は避け、テーマ側ヘルパーを使用する
        from classes.theme import get_qcolor

        def _qc(val: str):
            try:
                return get_qcolor(val)
            except Exception:
                return pal.color(QPalette.ColorRole.Window)

        mappings = [
            (QPalette.ColorRole.Window, ThemeKey.WINDOW_BACKGROUND),
            (QPalette.ColorRole.Base, ThemeKey.INPUT_BACKGROUND),
            (QPalette.ColorRole.AlternateBase, ThemeKey.PANEL_BACKGROUND),
            (QPalette.ColorRole.Text, ThemeKey.TEXT_PRIMARY),
            (QPalette.ColorRole.Button, ThemeKey.COMBO_BACKGROUND),  # QComboBox背景色強制（OS依存解消）
            (QPalette.ColorRole.ButtonText, ThemeKey.TEXT_PRIMARY),  # QComboBoxテキスト色統一
            (QPalette.ColorRole.Highlight, ThemeKey.TABLE_ROW_BACKGROUND_SELECTED),
            (QPalette.ColorRole.HighlightedText, ThemeKey.TABLE_ROW_TEXT_SELECTED),
            (QPalette.ColorRole.WindowText, ThemeKey.TEXT_PRIMARY),
            (QPalette.ColorRole.ToolTipBase, ThemeKey.PANEL_BACKGROUND),
            (QPalette.ColorRole.ToolTipText, ThemeKey.TEXT_PRIMARY),
            # placeholder は Active/Inactive と Disabled で色を分岐（無効 placeholder を確実に灰色系に）
            (QPalette.ColorRole.PlaceholderText, ThemeKey.INPUT_PLACEHOLDER),
        ]

        changed = 0
        skipped = 0
        for role, key in mappings:
            new_color = _qc(self.get_color(key))
            current_color = pal.color(role)
            if current_color != new_color:
                pal.setColor(role, new_color)
                changed += 1
            else:
                skipped += 1

        # Disabledグループのplaceholder色（無効時プレースホルダ）
        try:
            disabled_placeholder = _qc(self.get_color(ThemeKey.INPUT_PLACEHOLDER_DISABLED))
            current_disabled_placeholder = pal.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText)
            if current_disabled_placeholder != disabled_placeholder:
                pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText, disabled_placeholder)
                changed += 1
        except Exception:
            pass

        # 変更があった場合のみパレットを再設定
        if changed:
            app.setPalette(pal)
        print(f"[ThemeManager] QApplication palette applied(diff): changed={changed} skipped={skipped} mode={self._current_mode.value}")


# ========================================
# グローバルアクセス用のヘルパー関数
# ========================================

def get_theme_manager() -> ThemeManager:
    """ThemeManagerインスタンスを取得（グローバル関数）
    
    Returns:
        ThemeManagerインスタンス
        
    使用例:
        >>> from classes.theme import get_theme_manager, ThemeKey
        >>> theme = get_theme_manager()
        >>> color = theme.get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)
    """
    return ThemeManager.instance()


def get_color(key: ThemeKey) -> str:
    """現在のテーマから色を取得（グローバル関数）
    
    Args:
        key: テーマキー
        
    Returns:
        色文字列
        
    使用例:
        >>> from classes.theme import get_color, ThemeKey
        >>> bg_color = get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)
    """
    return ThemeManager.instance().get_color(key)


def get_qcolor(key: ThemeKey | str):
    """現在のテーマから QColor を取得（グローバル関数）

    直接 QColor() を呼ばずにテーマから色を取得したい場合に使用する。

    Args:
        key: テーマキー または 色文字列（#RRGGBB / rgba(...) など）

    Returns:
        PySide6.QtGui.QColor
    """
    from PySide6.QtGui import QColor

    def _parse_css_rgb_like(value: str) -> QColor | None:
        s = value.strip().lower()
        if not s:
            return None
        if s == "transparent":
            return QColor(0, 0, 0, 0)

        # rgba(r,g,b,a)  where a can be 0-1 float or 0-255 int
        if s.startswith("rgba(") and s.endswith(")"):
            try:
                inner = s[5:-1]
                parts = [p.strip() for p in inner.split(",")]
                if len(parts) != 4:
                    return None
                r = int(float(parts[0]))
                g = int(float(parts[1]))
                b = int(float(parts[2]))
                a_raw = float(parts[3])
                if a_raw <= 1.0:
                    a = int(round(a_raw * 255))
                else:
                    a = int(round(a_raw))
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))
                a = max(0, min(255, a))
                return QColor(r, g, b, a)
            except Exception:
                return None

        # rgb(r,g,b)
        if s.startswith("rgb(") and s.endswith(")"):
            try:
                inner = s[4:-1]
                parts = [p.strip() for p in inner.split(",")]
                if len(parts) != 3:
                    return None
                r = int(float(parts[0]))
                g = int(float(parts[1]))
                b = int(float(parts[2]))
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))
                return QColor(r, g, b, 255)
            except Exception:
                return None

        return None

    if isinstance(key, ThemeKey):
        value = get_color(key)
    else:
        value = key

    if isinstance(value, QColor):
        return value

    if isinstance(value, str):
        parsed = _parse_css_rgb_like(value)
        if parsed is not None:
            return parsed
        qc = QColor(value)
        if qc.isValid():
            return qc
        # Fallback: invalid strings become opaque black; be explicit.
        return QColor(0, 0, 0, 255)

    try:
        return QColor(value)
    except Exception:
        return QColor(0, 0, 0, 255)
