"""
データ登録タブウィジェット

データ登録機能のタブUI実装
- 通常登録タブ: 既存のデータ登録機能
- 一括登録タブ: 将来の一括登録機能（現在はプレースホルダー）
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel, QScrollArea, QSizePolicy, QApplication
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from .data_register_ui_creator import create_data_register_widget
from classes.data_entry.conf.ui_constants import (
    DATA_REGISTER_TAB_STYLE,
    DATA_REGISTER_FORM_STYLE,
    SCROLL_AREA_STYLE,
    TAB_HEIGHT_RATIO,
)


class DataRegisterTabWidget(QWidget):
    """データ登録機能のタブウィジェット"""
    

    def __init__(self, parent_controller, title="データ登録", button_style=None):
        super().__init__()
        self.parent_controller = parent_controller
        self.title = title
        self.button_style = button_style or "background-color: #2196f3; color: white; font-weight: bold; border-radius: 6px;"
        self._batch_tab_alert_shown = False  # 警告表示フラグ
        self._batch_tab_index = None
        self.setup_ui()
        
    def setup_ui(self):
        """UIのセットアップ"""
        # メインレイアウト
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)  # 余白をなくす
        main_layout.setSpacing(0)

        # タブウィジェット作成
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)

        # モダンなタブスタイル
        self.tab_widget.setStyleSheet(DATA_REGISTER_TAB_STYLE)

        # 通常登録タブ
        self.create_normal_register_tab()

        # 一括登録タブ
        self.create_batch_register_tab()

        # 一括登録タブのインデックスを記録（setup_uiの最後で）
        self._batch_tab_index = self.tab_widget.count() - 1

        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)

        # サイズポリシー設定（Expandingでウインドウサイズに追従）
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # タブ切り替え時のアスペクト比固定解除処理＆一括登録タブ警告
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.currentChanged.connect(self._on_tab_alert)
    def _on_tab_alert(self, index):
        """一括登録タブ選択時のみ警告を一度だけ表示"""
        if hasattr(self, '_batch_tab_index') and index == self._batch_tab_index and not self._batch_tab_alert_shown:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "ご注意", "この機能は開発中のため正しく動作しません。\n（テスト・検証目的以外での利用はお控えください）")
            self._batch_tab_alert_shown = True

        # 初期表示時にもタブごとのウインドウサイズ調整を反映
        current_index = self.tab_widget.currentIndex()
        self._on_tab_changed(current_index)

    def _on_tab_changed(self, index):
        """データ登録タブ選択時のウインドウサイズ調整"""
        # デバッグ出力
        print(f"[DEBUG] タブ変更: index={index}")

        top_level = self.window()
        screen = QApplication.primaryScreen()

        # --- ログイン・データ取得・データ取得2モードはウインドウサイズ調整をスキップ ---
        if top_level:
            win_title = top_level.windowTitle().lower()
            win_class = type(top_level).__name__.lower()
            if any(x in win_title for x in ["ログイン", "login", "データ取得", "data fetch", "datafetch2", "data取得2"]) or \
               any(x in win_class for x in ["login", "datafetch", "datafetch2"]):
                print(f"[DEBUG] ログイン・データ取得系ウインドウのためサイズ調整スキップ")
                return

        # 現在のウインドウサイズをデバッグ出力
        if top_level:
            current_size = top_level.size()
            print(f"[DEBUG] 現在のウインドウサイズ: {current_size.width()}x{current_size.height()}")
            print(f"[DEBUG] メインウィンドウ型: {type(top_level).__name__}")
            print(f"[DEBUG] メインウィンドウタイトル: {top_level.windowTitle()}")
            # サイズ制約の確認
            min_size = top_level.minimumSize()
            max_size = top_level.maximumSize()
            print(f"[DEBUG] 最小サイズ制約: {min_size.width()}x{min_size.height()}")
            print(f"[DEBUG] 最大サイズ制約: {max_size.width()}x{max_size.height()}")

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
                # 標準的な幅（データセット選択時に適切な幅）と95%高さを設定
                standard_width = 1200  # 通常登録タブの標準幅
                target_height = int(screen_size.height() * 0.95)
                
                print(f"[DEBUG] スクリーンサイズ: {screen_size.width()}x{screen_size.height()}")
                print(f"[DEBUG] 通常登録ターゲットサイズ: {standard_width}x{target_height} (幅=標準, 高さ=95%)")
                
                # サイズ制約をクリア
                if hasattr(top_level, 'setMinimumSize'):
                    top_level.setMinimumSize(200, 200)
                    print(f"[DEBUG] 最小サイズを200x200に設定")
                if hasattr(top_level, 'setMaximumSize'):
                    top_level.setMaximumSize(16777215, 16777215)
                    print(f"[DEBUG] 最大サイズを制限解除")
                
                # サイズポリシーを設定
                if hasattr(top_level, 'setSizePolicy'):
                    top_level.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    print(f"[DEBUG] サイズポリシーをPreferredに設定")
                
                if hasattr(top_level, 'showNormal'):
                    top_level.showNormal()
                    print(f"[DEBUG] showNormal()実行")
                if hasattr(top_level, 'resize'):
                    top_level.resize(standard_width, target_height)
                    print(f"[DEBUG] resize({standard_width}x{target_height})実行")
                    # リサイズ直後のサイズを確認
                    actual_size = top_level.size()
                    print(f"[DEBUG] リサイズ後の実際のサイズ: {actual_size.width()}x{actual_size.height()}")
                if hasattr(top_level, 'show'):
                    top_level.show()
                    print(f"[DEBUG] show()実行")
                    
                # 強制的にイベント処理を実行してからサイズを再確認
                QApplication.processEvents()
                final_size = top_level.size()
                print(f"[DEBUG] 最終確認サイズ: {final_size.width()}x{final_size.height()}")
                
        elif index == 1:  # 一括登録タブ
            # アスペクト比・横幅制限解除
            if hasattr(top_level, '_fixed_aspect_ratio'):
                top_level._fixed_aspect_ratio = None
            if hasattr(top_level, 'setMinimumWidth'):
                top_level.setMinimumWidth(200)
            if hasattr(top_level, 'setMaximumWidth'):
                top_level.setMaximumWidth(16777215)
                
            # 一括登録タブ：画面サイズの95%にリサイズ
            if screen:
                screen_size = screen.size()
                target_width = int(screen_size.width() * 0.95)
                target_height = int(screen_size.height() * 0.95)
                
                print(f"[DEBUG] スクリーンサイズ: {screen_size.width()}x{screen_size.height()}")
                print(f"[DEBUG] ターゲットサイズ(95%): {target_width}x{target_height}")
                
                # サイズ制約をクリア
                if hasattr(top_level, 'setMinimumSize'):
                    top_level.setMinimumSize(200, 200)
                    print(f"[DEBUG] 最小サイズを200x200に設定")
                if hasattr(top_level, 'setMaximumSize'):
                    top_level.setMaximumSize(16777215, 16777215)
                    print(f"[DEBUG] 最大サイズを制限解除")
                
                # サイズポリシーを設定
                if hasattr(top_level, 'setSizePolicy'):
                    top_level.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
                    print(f"[DEBUG] サイズポリシーをPreferredに設定")
                
                if hasattr(top_level, 'showNormal'):
                    top_level.showNormal()
                    print(f"[DEBUG] showNormal()実行")
                if hasattr(top_level, 'resize'):
                    top_level.resize(target_width, target_height)
                    print(f"[DEBUG] resize({target_width}x{target_height})実行")
                    # リサイズ直後のサイズを確認
                    actual_size = top_level.size()
                    print(f"[DEBUG] リサイズ後の実際のサイズ: {actual_size.width()}x{actual_size.height()}")
                if hasattr(top_level, 'show'):
                    top_level.show()
                    print(f"[DEBUG] show()実行")
                    
                # 強制的にイベント処理を実行してからサイズを再確認
                QApplication.processEvents()
                final_size = top_level.size()
                print(f"[DEBUG] 最終確認サイズ: {final_size.width()}x{final_size.height()}")
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

        # ▼ fieldset/legend風の枠組みをQGroupBoxで表現し、各エリアを分割
        # create_data_register_widget側で以下のQGroupBox構成になるよう修正してください:
        # 1. データセット選択エリア（QGroupBox, title="データセット選択"）
        # 2. 試料情報入力エリア（QGroupBox, title="試料情報入力"）
        # 3. 固有情報エリア（QGroupBox, title="固有情報"）
        # 4. データ情報入力エリア（QGroupBox, title="データ情報入力"）

        # スタイルでfieldset/legend風に装飾
        normal_widget.setStyleSheet(DATA_REGISTER_FORM_STYLE)

        # スクロールエリアでラップ
        scroll_area = QScrollArea()
        scroll_area.setWidget(normal_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # スクロールエリアのサイズポリシー設定
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        normal_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # スクロールエリアのスタイル
        scroll_area.setStyleSheet(SCROLL_AREA_STYLE)

        self.tab_widget.addTab(scroll_area, "通常登録")
        
    def create_batch_register_tab(self):
        """一括登録タブを作成"""
        from .batch_register_widget import BatchRegisterWidget
        # 一括登録ウィジェット作成
        batch_widget = BatchRegisterWidget(self.parent_controller)
        # スクロールエリアでラップ
        scroll_area = QScrollArea()
        scroll_area.setWidget(batch_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # スクロールエリアのサイズポリシー設定
        scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        batch_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # スクロールエリアのスタイル
        scroll_area.setStyleSheet(SCROLL_AREA_STYLE)
        self.tab_widget.addTab(scroll_area, "一括登録")
        
    def get_current_tab_index(self):
        """現在選択されているタブのインデックスを取得"""
        return self.tab_widget.currentIndex()
        
    def set_current_tab(self, index):
        """指定されたタブを選択"""
        self.tab_widget.setCurrentIndex(index)

    # resizeEventのオーバーライドは不要（ウインドウサイズ変更を妨げない）


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
