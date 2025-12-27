"""
データ取得2機能のタブウィジェット
画面サイズ適応型レスポンシブデザイン対応
"""

import logging
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

logger = logging.getLogger(__name__)

class DataFetch2TabWidget(QTabWidget):
    """データ取得2機能のタブウィジェット"""
    
    def __init__(self, parent=None, *, prewarm_filter_widget: bool = True):
        super().__init__(parent)
        self.parent_controller = parent
        self.bearer_token = None
        self._prewarm_filter_widget = bool(prewarm_filter_widget)
        
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
        
    def setup_ui(self):
        """UI初期化"""
        if not PYQT5_AVAILABLE:
            return
            
        # レスポンシブデザイン設定
        self.setup_responsive_layout()
        # データセット取得タブを追加
        self.create_dataset_tab()
        # フィルタタブ作成
        self.create_filter_tab()
        # 初期フィルタ状態の伝播（フィルタタブのデフォルトをデータ取得タブへ反映）
        self.init_filter_state()
        

        
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
                QTimer.singleShot(0, self._ensure_file_filter_widget)
        except Exception:
            pass

    def _on_tab_changed(self, index: int):
        try:
            if index == getattr(self, '_file_filter_tab_index', -1):
                self._ensure_file_filter_widget()
        except Exception:
            pass

    def _ensure_file_filter_widget(self):
        """必要ならFileFilterWidgetを構築してタブへ挿入（1回だけ）。"""
        if getattr(self, 'file_filter_widget', None) is not None:
            return

        try:
            from classes.utils.perf_monitor import PerfMonitor
        except Exception:
            PerfMonitor = None

        t0 = time.perf_counter()
        try:
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
        try:
            from classes.data_fetch2.core.ui.data_fetch2_widget import create_data_fetch2_widget
            # 既存の機能ウィジェットを統合
            tab_widget = create_data_fetch2_widget(self, self.bearer_token)
            if tab_widget:
                self.data_fetch_widget = tab_widget  # ウィジェットへの参照を保存
                self.addTab(tab_widget, "📊 データ取得")
                # 初期フィルタの表示を即時反映
                try:
                    if hasattr(self, 'current_filter_config') and hasattr(self.data_fetch_widget, 'set_filter_config_for_display'):
                        self.data_fetch_widget.set_filter_config_for_display(self.current_filter_config)
                except Exception:
                    pass
            else:
                # フォールバック
                fallback_widget = QWidget()
                fallback_layout = QVBoxLayout(fallback_widget)
                fallback_label = QLabel("データ取得機能は利用できません")
                fallback_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
                fallback_layout.addWidget(fallback_label)
                self.data_fetch_widget = None
                self.addTab(fallback_widget, "📊 データ取得")
        except ImportError as e:
            logger.error(f"データ取得ウィジェットのインポートエラー: {e}")
            fallback_widget = QWidget()
            fallback_layout = QVBoxLayout(fallback_widget)
            fallback_label = QLabel("データ取得機能は利用できません")
            fallback_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
            fallback_layout.addWidget(fallback_label)
            self.data_fetch_widget = None
            self.addTab(fallback_widget, "📊 データ取得")
            
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


def create_data_fetch2_tab_widget(parent=None, *, prewarm_filter_widget: bool = True):
    """データ取得2タブウィジェットを作成"""
    try:
        # prewarm_filter_widget=True が従来挙動（初回描画をブロックしないため遅延構築）
        return DataFetch2TabWidget(parent, prewarm_filter_widget=prewarm_filter_widget)
    except Exception as e:
        logger.error(f"データ取得2タブウィジェット作成エラー: {e}")
        return None
