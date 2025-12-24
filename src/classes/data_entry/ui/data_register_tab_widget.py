"""
データ登録タブウィジェット

データ登録機能のタブUI実装
- 通常登録タブ: 既存のデータ登録機能
- 一括登録タブ: 将来の一括登録機能（現在はプレースホルダー）
"""

import logging
import os
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel, QScrollArea, QSizePolicy, QApplication, QGroupBox
)
from qt_compat.core import QTimer, Qt
from qt_compat.gui import QFont

from .data_register_ui_creator import create_data_register_widget

# ロガー設定
logger = logging.getLogger(__name__)
from classes.data_entry.conf.ui_constants import (
    get_data_register_tab_style,
    get_data_register_form_style,
    get_scroll_area_style,
    TAB_HEIGHT_RATIO,
)


class DataRegisterTabWidget(QWidget):
    """データ登録機能のタブウィジェット"""
    

    def __init__(self, parent_controller, title="データ登録", button_style=None):
        super().__init__()
        self.parent_controller = parent_controller
        self.title = title
        # button_style は呼び出し元が指定した場合のみ使用し、未指定時は作成側でテーマ準拠のデフォルトを生成する。
        self.button_style = button_style
        self._batch_tab_alert_shown = False  # 警告表示フラグ
        self._normal_tab_index = None
        self._batch_tab_index = None
        self.setup_ui()
        
        # テーマ変更シグナルに接続（Singletonを必ず使用）
        try:
            from classes.theme.theme_manager import ThemeManager

            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        except Exception:
            pass
        

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)  # 余白をなくす
        main_layout.setSpacing(0)

        # タブウィジェット作成
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)

        # モダンなタブスタイル（ThemeKey適用）
        from classes.theme.theme_manager import get_color
        from classes.theme.theme_keys import ThemeKey
        tab_style = f"""
            QTabWidget {{
                background-color: {get_color(ThemeKey.DATA_ENTRY_TAB_CONTAINER_BACKGROUND)};
            }}
            QTabWidget::pane {{
                border: 1px solid {get_color(ThemeKey.TAB_BORDER)};
                background-color: {get_color(ThemeKey.TAB_BACKGROUND)};
            }}
            QTabBar::tab {{
                background-color: {get_color(ThemeKey.TAB_INACTIVE_BACKGROUND)};
                color: {get_color(ThemeKey.TAB_INACTIVE_TEXT)};
                padding: 8px 16px;
                border: 1px solid {get_color(ThemeKey.TAB_BORDER)};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {get_color(ThemeKey.TAB_ACTIVE_BACKGROUND)};
                color: {get_color(ThemeKey.TAB_ACTIVE_TEXT)};
                border-bottom: 2px solid {get_color(ThemeKey.TAB_ACTIVE_BORDER)};
            }}
            QTabBar::tab:hover {{
                background-color: {get_color(ThemeKey.MENU_ITEM_BACKGROUND_HOVER)};
            }}
        """
        self.tab_widget.setStyleSheet(tab_style)

        # 通常登録タブ
        self.create_normal_register_tab()

        # 一括登録タブ
        batch_index = self.create_batch_register_tab()

        # 登録状況タブ
        self.create_status_tab()

        # 一括登録タブのインデックスを記録（明示的に保持）
        self._batch_tab_index = batch_index

        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)

        # サイズポリシー設定（Expandingでウインドウサイズに追従）
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # タブ切り替え時のアスペクト比固定解除処理＆一括登録タブ警告
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.currentChanged.connect(self._on_tab_alert)
    
    def refresh_theme(self):
        """テーマ変更時のスタイル更新"""
        try:
            # タブ全体スタイル再生成
            tab_style = get_data_register_tab_style()
            self.tab_widget.setStyleSheet(tab_style)

            # 通常登録フォーム再適用
            if hasattr(self, 'normal_widget') and self.normal_widget:
                self.normal_widget.setStyleSheet(get_data_register_form_style())

            # create_data_register_widget が個別に styleSheet を持つラベルがあるため、ここで再生成する
            try:
                from classes.theme.theme_keys import ThemeKey
                from classes.theme.theme_manager import get_color

                tpl_label = getattr(self.parent_controller, 'template_format_label', None)
                if isinstance(tpl_label, QLabel) and tpl_label.parent() is not None:
                    tpl_label.setStyleSheet(
                        f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
                        f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; "
                        f"border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)}; border-radius: 4px;"
                    )

                fv_label = getattr(self.parent_controller, 'file_validation_label', None)
                if isinstance(fv_label, QLabel) and fv_label.parent() is not None:
                    fv_label.setStyleSheet(
                        f"padding: 8px; background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)}; "
                        f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; "
                        f"border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)}; border-radius: 4px;"
                    )
            except Exception:
                pass

            # 必須ラベルのエラー色は動的なため、テーマ切替時にも再評価
            try:
                updater = getattr(self.parent_controller, 'update_register_button_state', None)
                if callable(updater):
                    updater()
            except Exception:
                pass
            if hasattr(self, 'normal_register_scroll_area') and self.normal_register_scroll_area:
                self.normal_register_scroll_area.setStyleSheet(get_scroll_area_style())

            # 一括登録側スクロールエリア・内部ウィジェット再適用
            if hasattr(self, 'batch_register_scroll_area') and self.batch_register_scroll_area:
                self.batch_register_scroll_area.setStyleSheet(get_scroll_area_style())
            if hasattr(self, 'batch_widget') and self.batch_widget and hasattr(self.batch_widget, 'refresh_theme'):
                # 内部でさらに詳細要素を再適用
                self.batch_widget.refresh_theme()

            # 再描画
            self.tab_widget.update()
            # 大量項目を含むQComboBoxの高速化最適化
            try:
                from classes.utils.theme_perf_util import optimize_combo_boxes
                optimize_combo_boxes(self, threshold=500)
            except Exception:
                pass
            self.update()
            logger.debug("DataRegisterTabWidget: 動的スタイル再適用完了")
        except Exception as e:
            logger.error(f"DataRegisterTabWidget: テーマ更新エラー: {e}")

    def showEvent(self, event):  # type: ignore[override]
        super().showEvent(event)
        # 他ウィジェットから戻ってきた場合、タブ変更イベントが発火しないため
        # 現在タブに応じたサイズ調整を必ず再適用する。
        try:
            QTimer.singleShot(0, lambda: self._on_tab_changed(self.tab_widget.currentIndex()))
        except Exception:
            pass

    def event(self, event):  # type: ignore[override]
        # Windowsで表示復帰時にshowEventが来ないケース対策（WindowActivate）
        try:
            if event.type() == event.Type.WindowActivate:
                QTimer.singleShot(0, lambda: self._on_tab_changed(self.tab_widget.currentIndex()))
        except Exception:
            pass
        return super().event(event)
    
    def _on_tab_alert(self, index):
        """一括登録タブ選択時のみ警告を一度だけ表示"""
        if hasattr(self, '_batch_tab_index') and index == self._batch_tab_index and not self._batch_tab_alert_shown:
            # 開発完了のため、アラートをコメントアウト
            # from qt_compat.widgets import QMessageBox
            # QMessageBox.warning(self, "ご注意", "この機能は開発中のため正しく動作しません。\n（テスト・検証目的以外での利用はお控えください）")
            self._batch_tab_alert_shown = True

        # 初期表示時にもタブごとのウインドウサイズ調整を反映
        current_index = self.tab_widget.currentIndex()
        self._on_tab_changed(current_index)

    def _on_tab_changed(self, index):
        """データ登録タブ選択時のウインドウサイズ調整"""
        # デバッグ出力
        logger.debug("タブ変更: index=%s", index)

        top_level = self.window()
        screen = QApplication.primaryScreen()

        # --- ログイン・データ取得・データ取得2モードはウインドウサイズ調整をスキップ ---
        if top_level:
            win_title = top_level.windowTitle().lower()
            win_class = type(top_level).__name__.lower()
            if any(x in win_title for x in ["ログイン", "login", "データ取得", "data fetch", "datafetch2", "data取得2"]) or \
               any(x in win_class for x in ["login", "datafetch", "datafetch2"]):
                logger.debug("ログイン・データ取得系ウインドウのためサイズ調整スキップ")
                return

        # 現在のウインドウサイズをデバッグ出力
        if top_level:
            current_size = top_level.size()
            logger.debug("現在のウインドウサイズ: %sx%s", current_size.width(), current_size.height())
            logger.debug("メインウィンドウ型: %s", type(top_level).__name__)
            logger.debug("メインウィンドウタイトル: %s", top_level.windowTitle())
            # サイズ制約の確認
            min_size = top_level.minimumSize()
            max_size = top_level.maximumSize()
            logger.debug("最小サイズ制約: %sx%s", min_size.width(), min_size.height())
            logger.debug("最大サイズ制約: %sx%s", max_size.width(), max_size.height())

        if index == 0:  # 通常登録タブ
            # アスペクト比・横幅制限解除
            if hasattr(top_level, '_fixed_aspect_ratio'):
                top_level._fixed_aspect_ratio = None
            if hasattr(top_level, 'setMinimumWidth'):
                top_level.setMinimumWidth(200)
            if hasattr(top_level, 'setMaximumWidth'):
                top_level.setMaximumWidth(16777215)
                
            # 通常登録タブ：標準的なサイズに設定（初回呼び出し時と同じ幅・95%高さ）
            if screen:
                screen_size = screen.size()
                # 標準的な幅（データセット選択時に適切な幅）と90%高さを設定
                standard_width = 1200  # 通常登録タブの標準幅
                target_height = int(screen_size.height() * 0.90)

                logger.debug("スクリーンサイズ: %sx%s", screen_size.width(), screen_size.height())
                logger.debug("通常登録ターゲットサイズ: %sx%s (幅=標準, 高さ=95%%)", standard_width, target_height)
                
                # サイズ制約をクリア
                if hasattr(top_level, 'setMinimumSize'):
                    top_level.setMinimumSize(200, 200)
                    logger.debug("最小サイズを200x200に設定")
                if hasattr(top_level, 'setMaximumSize'):
                    top_level.setMaximumSize(16777215, 16777215)
                    logger.debug("最大サイズを制限解除")
                
                # サイズポリシーを設定
                if hasattr(top_level, 'setSizePolicy'):
                    top_level.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    logger.debug("サイズポリシーをPreferredに設定")
                
                if hasattr(top_level, 'showNormal'):
                    top_level.showNormal()
                    logger.debug("showNormal()実行")
                if hasattr(top_level, 'resize'):
                    top_level.resize(standard_width, target_height)
                    logger.debug("resize(%sx%s)実行", standard_width, target_height)
                    # リサイズ直後のサイズを確認
                    actual_size = top_level.size()
                    logger.debug("リサイズ後の実際のサイズ: %sx%s", actual_size.width(), actual_size.height())
                if hasattr(top_level, 'show'):
                    top_level.show()
                    logger.debug("show()実行")
                    
                # pytest中はWindowsで不安定になり得るため processEvents を避ける
                if not os.environ.get("PYTEST_CURRENT_TEST"):
                    QApplication.processEvents()
                final_size = top_level.size()
                logger.debug("最終確認サイズ: %sx%s", final_size.width(), final_size.height())
                
        elif index == 1:  # 一括登録タブ
            # アスペクト比・横幅制限解除
            if hasattr(top_level, '_fixed_aspect_ratio'):
                top_level._fixed_aspect_ratio = None
            if hasattr(top_level, 'setMinimumWidth'):
                top_level.setMinimumWidth(200)
            if hasattr(top_level, 'setMaximumWidth'):
                top_level.setMaximumWidth(16777215)

            # 一括登録タブ：画面サイズの90%にリサイズ
            if screen:
                screen_size = screen.size()
                target_width = int(screen_size.width() * 0.90)
                target_height = int(screen_size.height() * 0.90)
                
                logger.debug("スクリーンサイズ: %sx%s", screen_size.width(), screen_size.height())
                logger.debug("ターゲットサイズ(95%%): %sx%s", target_width, target_height)
                
                # サイズ制約をクリア
                if hasattr(top_level, 'setMinimumSize'):
                    top_level.setMinimumSize(200, 200)
                    logger.debug("最小サイズを200x200に設定")
                if hasattr(top_level, 'setMaximumSize'):
                    top_level.setMaximumSize(16777215, 16777215)
                    logger.debug("最大サイズを制限解除")
                
                # サイズポリシーを設定
                if hasattr(top_level, 'setSizePolicy'):
                    top_level.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    logger.debug("サイズポリシーをPreferredに設定")
                
                if hasattr(top_level, 'showNormal'):
                    top_level.showNormal()
                    logger.debug("showNormal()実行")
                if hasattr(top_level, 'resize'):
                    top_level.resize(target_width, target_height)
                    logger.debug("resize(%sx%s)実行", target_width, target_height)
                    # リサイズ直後のサイズを確認
                    actual_size = top_level.size()
                    logger.debug("リサイズ後の実際のサイズ: %sx%s", actual_size.width(), actual_size.height())
                if hasattr(top_level, 'show'):
                    top_level.show()
                    logger.debug("show()実行")
                    
                # pytest中はWindowsで不安定になり得るため processEvents を避ける
                if not os.environ.get("PYTEST_CURRENT_TEST"):
                    QApplication.processEvents()
                final_size = top_level.size()
                logger.debug("最終確認サイズ: %sx%s", final_size.width(), final_size.height())
        else:
            # 通常登録タブや他メニュー: 横幅900+メニュー+余白で固定、アスペクト比も固定
            webview_width = getattr(top_level, '_webview_fixed_width', 900)
            menu_width = 120
            margin = 40
            fixed_width = webview_width + menu_width + margin
            if hasattr(top_level, 'setFixedWidth'):
                top_level.setFixedWidth(fixed_width)
            if hasattr(top_level, '_fixed_aspect_ratio'):
                # 必ず900+メニュー+余白の幅と現在の高さでアスペクト比を再設定
                if hasattr(top_level, 'height') and top_level.height() != 0:
                    top_level._fixed_aspect_ratio = fixed_width / top_level.height()
                else:
                    top_level._fixed_aspect_ratio = 1.0

    # （高さ固定は行わず、ウインドウサイズに追従させる）
        
    def create_normal_register_tab(self):
        """通常登録タブを作成"""
        # 既存のデータ登録ウィジェットを使用
        normal_widget = create_data_register_widget(
            self.parent_controller, 
            self.title, 
            self.button_style
        )
        # 参照保持（テーマ変更時再スタイル用）
        self.normal_widget = normal_widget

        # ▼ fieldset/legend風の枠組みをQGroupBoxで表現し、各エリアを分割
        # create_data_register_widget側で以下のQGroupBox構成になるよう修正してください:
        # 1. データセット選択エリア（QGroupBox, title="データセット選択"）
        # 2. 試料情報入力エリア（QGroupBox, title="試料情報入力"）
        # 3. 固有情報エリア（QGroupBox, title="固有情報"）
        # 4. データ情報入力エリア（QGroupBox, title="データ情報入力"）

        # スタイルでfieldset/legend風に装飾（動的スタイル適用）
        normal_widget.setStyleSheet(get_data_register_form_style())

        # スクロールエリアでラップ
        scroll_area = QScrollArea()
        scroll_area.setWidget(normal_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # スクロールエリアのサイズポリシー設定
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        normal_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # スクロールエリアのスタイル（ThemeKey適用）
        from classes.theme.theme_manager import get_color
        from classes.theme.theme_keys import ThemeKey
        scroll_area_style = f"""
            QScrollArea {{
                background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)};
                border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)};
            }}
        """
        scroll_area.setStyleSheet(scroll_area_style)
        self.normal_register_scroll_area = scroll_area
        index = self.tab_widget.addTab(scroll_area, "通常登録")
        self._normal_tab_index = index
        
    def create_batch_register_tab(self):
        """一括登録タブを作成"""
        from .batch_register_widget import BatchRegisterWidget
        # 一括登録ウィジェット作成
        batch_widget = BatchRegisterWidget(self.parent_controller)
        self.batch_widget = batch_widget
        # スクロールエリアでラップ
        scroll_area = QScrollArea()
        scroll_area.setWidget(batch_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # スクロールエリアのサイズポリシー設定
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        batch_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # スクロールエリアのスタイル（ThemeKey適用）
        from classes.theme.theme_manager import get_color
        from classes.theme.theme_keys import ThemeKey
        scroll_area_style = f"""
            QScrollArea {{
                background-color: {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND)};
                border: 1px solid {get_color(ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER)};
            }}
        """
        scroll_area.setStyleSheet(scroll_area_style)
        self.batch_register_scroll_area = scroll_area
        idx = self.tab_widget.addTab(scroll_area, "一括登録")
        return idx

    def create_status_tab(self):
        """登録状況タブを作成"""
        try:
            from .registration_status_widget import RegistrationStatusWidget
            status_widget = RegistrationStatusWidget(self)
            # スクロールは不要なため直接追加（行数が多い場合は後でScrollArea化）
            self.tab_widget.addTab(status_widget, "登録状況")
        except Exception as e:
            logger.error(f"登録状況タブの作成に失敗: {e}")
        
    def get_current_tab_index(self):
        """現在選択されているタブのインデックスを取得"""
        return self.tab_widget.currentIndex()
        
    def set_current_tab(self, index):
        """指定されたタブを選択"""
        self.tab_widget.setCurrentIndex(index)
        try:
            self._on_tab_changed(index)
        except Exception:
            pass

    def focus_normal_register_tab(self) -> bool:
        """通常登録タブを前面に表示"""
        if not hasattr(self, 'tab_widget') or self.tab_widget is None:
            return False
        target_index = self._normal_tab_index if self._normal_tab_index is not None else 0
        if target_index < 0 or target_index >= self.tab_widget.count():
            return False
        try:
            if self.tab_widget.currentIndex() != target_index:
                self.tab_widget.setCurrentIndex(target_index)
        except Exception as exc:
            logger.debug("DataRegisterTabWidget: 通常登録タブへのフォーカスに失敗: %s", exc)
            return False
        return True

    def focus_batch_register_tab(self) -> bool:
        """一括登録タブを前面に表示"""
        if not hasattr(self, 'tab_widget') or self.tab_widget is None:
            return False
        target_index = self._batch_tab_index if self._batch_tab_index is not None else 1
        if target_index < 0 or target_index >= self.tab_widget.count():
            return False
        try:
            if self.tab_widget.currentIndex() != target_index:
                self.tab_widget.setCurrentIndex(target_index)
        except Exception as exc:
            logger.debug("DataRegisterTabWidget: 一括登録タブへのフォーカスに失敗: %s", exc)
            return False
        return True

    # resizeEventのオーバーライドは不要（ウインドウサイズ変更を妨げない）

    def show_status_after_single(self, data_item: dict):
        """通常登録完了後に、最新1件＋総件数を表示するダイアログを開く。
        data_item: 登録に使用した dataEntry 形式の1アイテム（id/attributes/relationships を含む）
        """
        try:
            # dataset 名取得（dataset_dropdownの型に応じて）
            dataset_name = None
            combo = None
            if hasattr(self.parent_controller, 'dataset_dropdown'):
                dd = self.parent_controller.dataset_dropdown
                if hasattr(dd, 'dataset_dropdown'):
                    combo = dd.dataset_dropdown
                elif hasattr(dd, 'dataset_filter_widget') and hasattr(dd.dataset_filter_widget, 'dataset_dropdown'):
                    combo = dd.dataset_filter_widget.dataset_dropdown
                elif getattr(dd, 'currentText', None):
                    combo = dd
            if combo and getattr(combo, 'currentText', None):
                dataset_name = combo.currentText()

            from .registration_status_dialog import show_status_dialog_for_single
            show_status_dialog_for_single(self, dataset_name or '', data_item)
        except Exception as e:
            logger.error(f"通常登録後ステータスダイアログ表示エラー: {e}")

    def show_status_after_batch(self, data_items: list):
        """一括登録完了後に、全ファイルセットの登録状況をまとめて表示するダイアログを開く。"""
        try:
            dataset_name = None
            combo = None
            if hasattr(self.parent_controller, 'dataset_dropdown'):
                dd = self.parent_controller.dataset_dropdown
                if hasattr(dd, 'dataset_dropdown'):
                    combo = dd.dataset_dropdown
                elif hasattr(dd, 'dataset_filter_widget') and hasattr(dd.dataset_filter_widget, 'dataset_dropdown'):
                    combo = dd.dataset_filter_widget.dataset_dropdown
                elif getattr(dd, 'currentText', None):
                    combo = dd
            if combo and getattr(combo, 'currentText', None):
                dataset_name = combo.currentText()

            from .registration_status_dialog import show_status_dialog_for_batch
            show_status_dialog_for_batch(self, dataset_name or '', data_items)
        except Exception as e:
            logger.error(f"一括登録後ステータスダイアログ表示エラー: {e}")


def create_data_register_tab_widget(parent_controller, title="データ登録", button_style=None):
    """
    データ登録タブウィジェットを作成
    
    Args:
        parent_controller: 親のUIController
        title: ウィジェットのタイトル
        button_style: ボタンのスタイル
        
    Returns:
        DataRegisterTabWidget: データ登録タブウィジェット
    """
    return DataRegisterTabWidget(parent_controller, title, button_style)
