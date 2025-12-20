"""
テーマ管理 - ARIM RDE Tool v2.1.6

ライト/ダークテーマの切り替えとカラー取得を一元管理。
Singleton パターンで全UI要素から参照可能。
"""

from enum import Enum
from typing import Optional
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
        import time
        total_start = time.perf_counter_ns()
        
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
                try:
                    top_levels = [w for w in QApplication.topLevelWidgets() if hasattr(w, 'setUpdatesEnabled')]
                except Exception:
                    top_levels = []
                for w in top_levels:
                    try:
                        w.setUpdatesEnabled(False)
                    except Exception:
                        pass
                # グローバルスタイル適用
                # --- Style Phase Micro Profiling ---
                from .global_styles import get_global_base_style  # type: ignore
                import hashlib

                style_phase_start = time.perf_counter_ns()
                # (1) Generation (or cache retrieval)
                gen_start = time.perf_counter_ns()
                cached = False
                qss = self._global_style_cache.get(self._current_mode)
                if qss is None:
                    qss = get_global_base_style()
                    self._global_style_cache[self._current_mode] = qss
                    gen_elapsed = (time.perf_counter_ns() - gen_start) / 1_000_000
                    print(f"[ThemeManager] global QSS generated ({gen_elapsed:.2f}ms, mode={self._current_mode.value}, length={len(qss)})")
                else:
                    cached = True
                    gen_elapsed = (time.perf_counter_ns() - gen_start) / 1_000_000
                    print(f"[ThemeManager] global QSS cache hit (mode={self._current_mode.value}, length={len(qss)})")

                # (2) Hash comparison + (conditional) application
                apply_start = time.perf_counter_ns()
                style_hash = hashlib.sha256(qss.encode('utf-8')).hexdigest()
                apply_skipped = False
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
                
                # 大量ComboBox最適化
                combo_elapsed = 0.0
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
                # Process pending events to realize repaint/layout cost
                try:
                    app.processEvents()
                except Exception:
                    pass
                # Optional targeted update
                for w in top_levels:
                    try:
                        if hasattr(w, 'update'):
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
        from PySide6.QtGui import QColor

        def _qc(val: str):
            try:
                return QColor(val)
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
            (QPalette.ColorRole.PlaceholderText, ThemeKey.TEXT_PLACEHOLDER),
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
