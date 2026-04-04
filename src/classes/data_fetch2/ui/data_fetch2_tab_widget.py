"""
データ取得2機能のタブウィジェット
画面サイズ適応型レスポンシブデザイン対応
"""

import logging
import os
from typing import Optional
import time

try:
    from qt_compat.widgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
        QLabel, QPushButton, QLineEdit, QApplication,
        QScrollArea, QGroupBox, QGridLayout, QComboBox,
        QTextEdit, QListWidget, QTreeWidget, QTreeWidgetItem,
        QCheckBox, QSpinBox
    )
    from qt_compat.core import Qt
    from qt_compat.core import QTimer
    from qt_compat.gui import QFont
    PYQT5_AVAILABLE = True
except ImportError:
    PYQT5_AVAILABLE = False
    class QWidget: pass
    class QTabWidget: pass

from classes.theme import ThemeKey
from classes.theme.theme_manager import get_color
from classes.utils.ui_responsiveness import schedule_deferred_ui_task, start_ui_responsiveness_run

logger = logging.getLogger(__name__)

class DataFetch2TabWidget(QTabWidget):
    """データ取得2機能のタブウィジェット"""
    
    def __init__(self, parent=None, *, prewarm_filter_widget: bool = True, prewarm_dataset_widget: bool = True, prewarm_filter_delay_ms: int | None = None, prewarm_dataset_delay_ms: int | None = None):
        super().__init__(parent)
        self.parent_controller = parent
        self.bearer_token = None
        self._prewarm_filter_widget = bool(prewarm_filter_widget)
        self._prewarm_dataset_widget = bool(prewarm_dataset_widget)
        self._prewarm_filter_delay_ms = self._resolve_filter_prewarm_delay(prewarm_filter_delay_ms)
        self._prewarm_dataset_delay_ms = self._resolve_dataset_prewarm_delay(prewarm_dataset_delay_ms)
        self.data_fetch_widget = None
        
        # フィルタ設定の初期化
        try:
            from classes.data_fetch2.conf.file_filter_config import get_default_filter
            self.current_filter_config = get_default_filter()
        except ImportError:
            # フォールバック
            self.current_filter_config = {
                "file_types": ["MAIN_IMAGE"],
                "media_types": [],
                "extensions": [],
                "size_min": 0,
                "size_max": 0,
                "filename_pattern": "",
                "max_download_count": 0
            }
        
        self.setup_ui()
        
    def set_bearer_token(self, token):
        """Bearer tokenを設定"""
        self.bearer_token = token
        try:
            if self.data_fetch_widget and hasattr(self.data_fetch_widget, 'set_bearer_token'):
                self.data_fetch_widget.set_bearer_token(token)
        except Exception:
            logger.debug("data_fetch2: failed to propagate bearer token", exc_info=True)

    def _resolve_filter_prewarm_delay(self, explicit_delay_ms: int | None) -> int:
        if explicit_delay_ms is not None:
            return max(0, int(explicit_delay_ms))
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return 0
        return 1500

    def _resolve_dataset_prewarm_delay(self, explicit_delay_ms: int | None) -> int:
        if explicit_delay_ms is not None:
            return max(0, int(explicit_delay_ms))
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return 0
        return 180
        
    def setup_ui(self):
        """UI初期化"""
        if not PYQT5_AVAILABLE:
            return
            
        # レスポンシブデザイン設定
        self.setup_responsive_layout()
        # データセット取得タブを追加
        self.create_dataset_tab()
        # 一括取得（RDE）タブを追加
        self.create_bulk_rde_tab()
        # 一括取得（DP）タブを追加
        self.create_bulk_dp_tab()
        # フィルタタブ作成
        self.create_filter_tab()
        # 初期フィルタ状態の伝播（フィルタタブのデフォルトをデータ取得タブへ反映）
        self.init_filter_state()

    def _wrap_tab_widget(self, content_widget: QWidget, object_name: str) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setObjectName(object_name)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        container = QWidget(scroll)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(content_widget)
        container_layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    def _create_loading_panel(self, message: str) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return panel

    def _replace_tab_widget(self, index: int, widget: QWidget, title: str) -> None:
        try:
            self.blockSignals(True)
            self.removeTab(index)
            self.insertTab(index, widget, title)
            self.setCurrentIndex(index)
        finally:
            try:
                self.blockSignals(False)
            except Exception:
                pass
        

        
    def setup_responsive_layout(self):
        """レスポンシブレイアウト設定"""
        # 画面サイズ取得 - PySide6対応
        from qt_compat import get_screen_size
        screen_width, _ = get_screen_size(self)
        
        # レスポンシブ設定
        self.columns = self.get_optimal_layout_columns(screen_width)
        
    def get_optimal_layout_columns(self, width=None):
        """最適な段組数を取得"""
        if width is None:
            from qt_compat import get_screen_size
            width, _ = get_screen_size(self)
            
        if width < 1024:
            return 1  # 1段組（スクロール表示）
        elif width < 1440:
            return 2  # 2段組（左右分割）
        else:
            return 3  # 3段組（左中右分割）
            
    # 不要なメソッドを削除: create_search_tab, create_download_tab
    # フィルタ設定とデータ取得のみに機能を集約
    
    def create_filter_tab(self):
        """ファイルフィルタタブ - 高度なフィルタ機能"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # タイトル
        title_label = QLabel("ファイルフィルタ設定")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # 説明
        desc_label = QLabel("データ取得タブで一括取得するファイルの種類や条件を指定します")
        desc_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_MUTED)}; margin-bottom: 10px;")
        layout.addWidget(desc_label)

        # 重いFileFilterWidgetは、ウィンドウ初回描画をブロックしないように遅延構築する。
        # ただしユーザーがタブを開く頃には構築済みになるよう、イベントループが回った後に自動でプレウォームする。
        self.file_filter_widget = None
        self._file_filter_container = QWidget(tab_widget)
        self._file_filter_container_layout = QVBoxLayout(self._file_filter_container)
        self._file_filter_container_layout.setContentsMargins(0, 0, 0, 0)
        self._file_filter_placeholder = QLabel("読み込み中…")
        self._file_filter_container_layout.addWidget(self._file_filter_placeholder)
        # コンテナがタブ領域の高さに追従して伸びるようストレッチを付ける
        layout.addWidget(self._file_filter_container, 1)

        self._file_filter_tab_index = self.addTab(tab_widget, "🔍 ファイルフィルタ")

        # タブ選択時に未構築なら構築
        try:
            self.currentChanged.connect(self._on_tab_changed)
        except Exception:
            pass

        # プレウォーム（初回描画のあとに構築）
        try:
            if self._prewarm_filter_widget:
                QTimer.singleShot(self._prewarm_filter_delay_ms, self._ensure_file_filter_widget)
        except Exception:
            pass

    def _on_tab_changed(self, index: int):
        try:
            if index == getattr(self, '_dataset_tab_index', -1):
                run = start_ui_responsiveness_run("data_fetch2", "dataset_tab", "lazy_tab_build", tab_index=index, cache_state="miss")
                run.mark("placeholder_visible")
                schedule_deferred_ui_task(self, "data-fetch2-dataset-tab", lambda session=run: self._ensure_dataset_widget(session))
            if index == getattr(self, '_bulk_rde_tab_index', -1):
                run = start_ui_responsiveness_run("data_fetch2", "bulk_rde_tab", "lazy_tab_build", tab_index=index, cache_state="miss")
                run.mark("placeholder_visible")
                schedule_deferred_ui_task(self, "data-fetch2-bulk-rde-tab", lambda session=run: self._ensure_bulk_rde_widget(session))
            elif index == getattr(self, '_bulk_dp_tab_index', -1):
                run = start_ui_responsiveness_run("data_fetch2", "bulk_dp_tab", "lazy_tab_build", tab_index=index, cache_state="miss")
                run.mark("placeholder_visible")
                schedule_deferred_ui_task(self, "data-fetch2-bulk-dp-tab", lambda session=run: self._ensure_bulk_dp_widget(session))
            if index == getattr(self, '_file_filter_tab_index', -1):
                run = start_ui_responsiveness_run("data_fetch2", "filter_tab", "lazy_tab_build", tab_index=index, cache_state="miss")
                run.mark("placeholder_visible")
                schedule_deferred_ui_task(self, "data-fetch2-filter-tab", lambda session=run: self._ensure_file_filter_widget(session))
        except Exception:
            pass

    def _ensure_bulk_rde_widget(self, run=None):
        if getattr(self, 'bulk_rde_widget', None) is not None:
            if run is not None:
                run.finish(success=True, cache_state="memory_hit")
            return

        from classes.data_fetch2.ui.bulk_rde_tab import create_bulk_rde_tab

        if run is not None:
            run.mark("build_start")
        tab_widget = create_bulk_rde_tab(self)
        self.bulk_rde_widget = tab_widget
        try:
            if hasattr(tab_widget, 'set_filter_config'):
                tab_widget.set_filter_config(self.current_filter_config)
        except Exception:
            pass
        wrapped = self._wrap_tab_widget(tab_widget, 'dataFetch2BulkRdeScrollArea')
        self._replace_tab_widget(self._bulk_rde_tab_index, wrapped, '📦 一括取得（RDE）')
        if run is not None:
            run.interactive(widget_class=type(tab_widget).__name__)
            run.complete(widget_class=type(tab_widget).__name__)
            run.finish(success=True)

    def _ensure_dataset_widget(self, run=None):
        if getattr(self, 'data_fetch_widget', None) is not None:
            if run is not None:
                run.finish(success=True, cache_state="memory_hit")
            return

        t0 = time.perf_counter()
        # 構築中のレイアウト再計算・再描画を抑制（2921項目のsizeHint走査を回避）
        self.setUpdatesEnabled(False)
        try:
            if run is not None:
                run.mark("build_start")
            from classes.data_fetch2.core.ui.data_fetch2_widget import create_data_fetch2_widget

            tab_widget = create_data_fetch2_widget(self, self.bearer_token)
            t1 = time.perf_counter()
            if tab_widget:
                self.data_fetch_widget = tab_widget
                try:
                    if hasattr(self, 'current_filter_config') and hasattr(self.data_fetch_widget, 'set_filter_config_for_display'):
                        self.data_fetch_widget.set_filter_config_for_display(self.current_filter_config)
                except Exception:
                    pass
                wrapped = self._wrap_tab_widget(tab_widget, 'dataFetch2DatasetScrollArea')
                self._replace_tab_widget(self._dataset_tab_index, wrapped, '📊 データ取得')
                t2 = time.perf_counter()
                logger.info(
                    "data_fetch2: _ensure_dataset_widget create=%.3fs replace=%.3fs total=%.3fs",
                    t1 - t0, t2 - t1, t2 - t0,
                )
                if run is not None:
                    run.interactive(widget_class=type(tab_widget).__name__, create_ms=round((t1 - t0) * 1000.0, 3))
                    run.complete(widget_class=type(tab_widget).__name__, total_ms=round((t2 - t0) * 1000.0, 3))
                    run.finish(success=True)
                return
        except ImportError as e:
            logger.error(f"データ取得ウィジェットのインポートエラー: {e}")
            if run is not None:
                run.finish(success=False, error=str(e))
        except Exception as e:
            logger.error(f"データ取得ウィジェット作成エラー: {e}")
            if run is not None:
                run.finish(success=False, error=str(e))
        finally:
            self.setUpdatesEnabled(True)

        fallback_widget = QWidget()
        fallback_layout = QVBoxLayout(fallback_widget)
        fallback_label = QLabel("データ取得機能は利用できません")
        fallback_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
        fallback_layout.addWidget(fallback_label)
        self.data_fetch_widget = None
        self._replace_tab_widget(self._dataset_tab_index, fallback_widget, '📊 データ取得')

    def _ensure_bulk_dp_widget(self, run=None):
        if getattr(self, 'bulk_dp_widget', None) is not None:
            if run is not None:
                run.finish(success=True, cache_state="memory_hit")
            return

        from classes.data_fetch2.ui.bulk_dp_tab import create_bulk_dp_tab

        if run is not None:
            run.mark("build_start")
        tab_widget = create_bulk_dp_tab(self)
        self.bulk_dp_widget = tab_widget
        wrapped = self._wrap_tab_widget(tab_widget, 'dataFetch2BulkDpScrollArea')
        self._replace_tab_widget(self._bulk_dp_tab_index, wrapped, '🌐 一括取得（DP）')
        if run is not None:
            run.interactive(widget_class=type(tab_widget).__name__)
            run.complete(widget_class=type(tab_widget).__name__)
            run.finish(success=True)

    def _ensure_file_filter_widget(self, run=None):
        """必要ならFileFilterWidgetを構築してタブへ挿入（1回だけ）。"""
        if getattr(self, 'file_filter_widget', None) is not None:
            if run is not None:
                run.finish(success=True, cache_state="memory_hit")
            return

        try:
            from classes.utils.perf_monitor import PerfMonitor
        except Exception:
            PerfMonitor = None

        t0 = time.perf_counter()
        try:
            if run is not None:
                run.mark("build_start")
            from classes.data_fetch2.ui.file_filter_widget import create_file_filter_widget
            widget = create_file_filter_widget(self._file_filter_container)
            widget.filterChanged.connect(self.on_file_filter_changed)

            # 現在のフィルタ状態があれば、初期反映（大量setCheckedのシグナル連発を避けるためウィジェット側で抑止する）
            try:
                if hasattr(self, 'current_filter_config') and self.current_filter_config:
                    if hasattr(widget, 'set_filter_config'):
                        widget.set_filter_config(self.current_filter_config)
            except Exception:
                pass

            # プレースホルダを置き換える
            try:
                if getattr(self, '_file_filter_placeholder', None) is not None:
                    self._file_filter_placeholder.setParent(None)
                    self._file_filter_placeholder = None
            except Exception:
                pass
            self._file_filter_container_layout.addWidget(widget)
            self.file_filter_widget = widget
            t1 = time.perf_counter()
            logger.info(f"[DataFetch2TabWidget] FileFilterWidget build: {t1 - t0:.3f} sec")
            if run is not None:
                run.interactive(widget_class=type(widget).__name__)
                run.complete(widget_class=type(widget).__name__, total_ms=round((t1 - t0) * 1000.0, 3))
                run.finish(success=True)
            try:
                if PerfMonitor is not None:
                    PerfMonitor.mark(
                        "data_fetch2:file_filter_widget:built",
                        logger=logging.getLogger("RDE_WebView"),
                        build_sec=round(t1 - t0, 6),
                    )
            except Exception:
                pass
        except ImportError as e:
            logger.error(f"フィルタウィジェットのインポートに失敗: {e}")
            if run is not None:
                run.finish(success=False, error=str(e))
            try:
                if getattr(self, '_file_filter_placeholder', None) is not None:
                    self._file_filter_placeholder.setText("高度なフィルタ機能は利用できません")
                    self._file_filter_placeholder.setStyleSheet(
                        f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;"
                    )
            except Exception:
                pass
        
    def create_dataset_tab(self):
        """データセット選択・取得タブ"""
        self.data_fetch_widget = None
        placeholder = self._create_loading_panel('データ取得タブを読み込み中...')
        wrapped = self._wrap_tab_widget(placeholder, 'dataFetch2DatasetScrollArea')
        self._dataset_tab_index = self.addTab(wrapped, '📊 データ取得')
        try:
            if self._prewarm_dataset_widget:
                run = start_ui_responsiveness_run("data_fetch2", "dataset_tab", "lazy_tab_build", tab_index=self._dataset_tab_index, cache_state="miss", trigger="initial_prewarm")
                run.mark("placeholder_visible")
                schedule_deferred_ui_task(
                    self,
                    "data-fetch2-dataset-tab-prewarm",
                    lambda session=run: self._ensure_dataset_widget(session),
                    delay_ms=self._prewarm_dataset_delay_ms,
                )
        except Exception:
            pass

    def create_mail_notification_tab(self):
        pass  # メール通知タブの作成を削除

    def create_bulk_rde_tab(self):
        """一括取得（RDE）タブ"""
        try:
            self.bulk_rde_widget = None
            placeholder = self._create_loading_panel('一括取得（RDE）タブを読み込み中...')
            wrapped = self._wrap_tab_widget(placeholder, 'dataFetch2BulkRdeScrollArea')
            self._bulk_rde_tab_index = self.addTab(wrapped, '📦 一括取得（RDE）')
        except Exception as e:
            logger.error(f"一括取得（RDE）タブ作成エラー: {e}")
            fallback_widget = QWidget()
            fallback_layout = QVBoxLayout(fallback_widget)
            fallback_label = QLabel("一括取得（RDE）機能は利用できません")
            fallback_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
            fallback_layout.addWidget(fallback_label)
            self.bulk_rde_widget = None
            self.addTab(fallback_widget, "📦 一括取得（RDE）")

    def create_bulk_dp_tab(self):
        """一括取得（DP）タブ"""
        try:
            self.bulk_dp_widget = None
            placeholder = self._create_loading_panel('一括取得（DP）タブを読み込み中...')
            wrapped = self._wrap_tab_widget(placeholder, 'dataFetch2BulkDpScrollArea')
            self._bulk_dp_tab_index = self.addTab(wrapped, '🌐 一括取得（DP）')
        except Exception as e:
            logger.error(f"一括取得（DP）タブ作成エラー: {e}")
            fallback_widget = QWidget()
            fallback_layout = QVBoxLayout(fallback_widget)
            fallback_label = QLabel("一括取得（DP）機能は利用できません")
            fallback_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
            fallback_layout.addWidget(fallback_label)
            self.bulk_dp_widget = None
            self.addTab(fallback_widget, "🌐 一括取得（DP）")
            
    def on_file_filter_changed(self, filter_config):
        """ファイルフィルタ変更時のハンドラー"""
        logger.info(f"フィルタ設定変更: {filter_config}")
        # フィルタ設定を保存
        self.current_filter_config = filter_config
        
        # フィルタ概要を表示（オプション）
        try:
            from classes.data_fetch2.util.file_filter_util import get_filter_summary
            summary = get_filter_summary(filter_config)
            logger.debug(f"フィルタ概要: {summary}")
        except ImportError:
            pass
        
        # データ取得タブのフィルタ状態表示を更新（直接反映を優先）
        try:
            if hasattr(self, 'data_fetch_widget') and self.data_fetch_widget and hasattr(self.data_fetch_widget, 'set_filter_config_for_display'):
                self.data_fetch_widget.set_filter_config_for_display(filter_config)
                logger.debug("フィルタ変更内容をデータ取得タブへ直接反映しました")
            else:
                self.update_data_fetch_filter_status()
        except Exception as e:
            logger.debug(f"直接反映エラー: {e}")
            self.update_data_fetch_filter_status()

        try:
            if hasattr(self, 'bulk_rde_widget') and self.bulk_rde_widget and hasattr(self.bulk_rde_widget, 'set_filter_config'):
                self.bulk_rde_widget.set_filter_config(filter_config)
        except Exception as e:
            logger.debug(f"RDE一括取得タブへのフィルタ伝播エラー: {e}")
    
    def update_data_fetch_filter_status(self):
        """データ取得タブのフィルタ状態表示を更新"""
        try:
            if hasattr(self, 'data_fetch_widget') and self.data_fetch_widget:
                # 直接設定が可能ならそれを使い、無ければ自己更新を呼ぶ
                if hasattr(self.data_fetch_widget, 'set_filter_config_for_display'):
                    self.data_fetch_widget.set_filter_config_for_display(self.current_filter_config)
                    logger.debug("データ取得タブへフィルタ設定を直接反映しました")
                elif hasattr(self.data_fetch_widget, 'update_filter_status_display'):
                    self.data_fetch_widget.update_filter_status_display()
                    logger.debug("データ取得タブのフィルタ状態表示を更新しました")
        except Exception as e:
            logger.debug(f"フィルタ状態表示更新エラー: {e}")

    def init_filter_state(self):
        """初期フィルタ状態の同期を実施"""
        try:
            if hasattr(self, 'file_filter_widget') and self.file_filter_widget:
                # フィルタタブの現在値（デフォルト）を取得して反映
                default_config = getattr(self.file_filter_widget, 'filter_config', None)
                # 防御的に空構成ならデフォルトを使用
                if not default_config or not default_config.get("file_types"):
                    from classes.data_fetch2.conf.file_filter_config import get_default_filter
                    default_config = get_default_filter()
                logger.debug(f"初期フィルタ状態を同期: {default_config}")
                self.current_filter_config = default_config
                self.update_data_fetch_filter_status()
        except Exception as e:
            logger.debug(f"初期フィルタ同期エラー: {e}")


def create_data_fetch2_tab_widget(parent=None, *, prewarm_filter_widget: bool = True, prewarm_dataset_widget: bool = True, prewarm_filter_delay_ms: int | None = None, prewarm_dataset_delay_ms: int | None = None):
    """データ取得2タブウィジェットを作成"""
    try:
        # prewarm_filter_widget=True が従来挙動（初回描画をブロックしないため遅延構築）
        return DataFetch2TabWidget(
            parent,
            prewarm_filter_widget=prewarm_filter_widget,
            prewarm_dataset_widget=prewarm_dataset_widget,
            prewarm_filter_delay_ms=prewarm_filter_delay_ms,
            prewarm_dataset_delay_ms=prewarm_dataset_delay_ms,
        )
    except Exception as e:
        logger.error(f"データ取得2タブウィジェット作成エラー: {e}")
        return None
