"""
データセット開設・編集のタブ付きウィジェット
"""
import os
from qt_compat.widgets import QWidget, QVBoxLayout, QLabel, QTabWidget
from classes.dataset.core.dataset_open_logic import create_group_select_widget


def create_dataset_open_widget(parent, title, color, create_auto_resize_button):
    """データセット開設・編集のタブ付きウィジェット"""
    # メインコンテナ
    main_widget = QWidget()
    main_layout = QVBoxLayout()
    
    # タイトル
    label = QLabel(f"{title}機能")
    label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1976d2; padding: 10px;")
    #main_layout.addWidget(label)
    
    # タブウィジェット
    tab_widget = QTabWidget()
    
    # 新規開設タブ
    try:
        create_tab_result = create_group_select_widget(parent)
        if create_tab_result and len(create_tab_result) >= 1:
            create_tab = create_tab_result[0]  # containerウィジェットを取得
            tab_widget.addTab(create_tab, "新規開設")
            # 新しい戻り値形式に対応: container, team_groups, combo, grant_combo, open_btn, name_edit, embargo_edit, template_combo, template_list
        else:
            # フォールバック：空のウィジェット
            from qt_compat.widgets import QLabel as FallbackLabel
            fallback_widget = QWidget()
            fallback_layout = QVBoxLayout()
            fallback_layout.addWidget(FallbackLabel("データセット開設機能を読み込み中..."))
            fallback_widget.setLayout(fallback_layout)
            tab_widget.addTab(fallback_widget, "新規開設")
    except Exception as e:
        print(f"[WARNING] データセット開設タブの作成に失敗: {e}")
        # エラー時は空のタブを作成
        from qt_compat.widgets import QLabel as ErrorLabel
        error_widget = QWidget()
        error_layout = QVBoxLayout()
        error_layout.addWidget(ErrorLabel(f"データセット開設機能の読み込みに失敗しました: {e}"))
        error_widget.setLayout(error_layout)
        tab_widget.addTab(error_widget, "新規開設")
    
    # 編集タブ
    try:
        from classes.dataset.ui.dataset_edit_widget import create_dataset_edit_widget
        edit_tab = create_dataset_edit_widget(parent, "データセット編集", color, create_auto_resize_button)
        tab_widget.addTab(edit_tab, "修正")
        
    except Exception as e:
        print(f"[WARNING] データセット編集タブの作成に失敗: {e}")
        # エラー時は新規開設のみ
    
    # データエントリータブ（最小版）
    try:
        from classes.dataset.ui.dataset_dataentry_widget_minimal import create_dataset_dataentry_widget
        dataentry_tab = create_dataset_dataentry_widget(parent, "データエントリー", color, create_auto_resize_button)
        tab_widget.addTab(dataentry_tab, "タイル（データエントリー）")
        
    except Exception as e:
        print(f"[WARNING] データエントリータブの作成に失敗: {e}")
        # エラー時は空のタブを作成
        from qt_compat.widgets import QLabel as ErrorLabel
        error_widget = QWidget()
        error_layout = QVBoxLayout()
        error_layout.addWidget(ErrorLabel(f"データエントリー機能の読み込みに失敗しました: {e}"))
        error_widget.setLayout(error_layout)
        tab_widget.addTab(error_widget, "データエントリー")
    
    # タブ切り替え時にデータセットリストをリフレッシュする機能を追加
    def on_tab_changed(index):
        """タブ切り替え時の処理"""
        try:
            # 修正タブ（インデックス1）が選択された場合
            if index == 1:  # 0: 新規開設, 1: 修正, 2: データエントリー
                print("[INFO] 修正タブが選択されました - データセットリストをリフレッシュします")
                # edit_tab内のload_existing_datasets関数を呼び出し
                try:
                    if hasattr(edit_tab, '_refresh_dataset_list'):
                        edit_tab._refresh_dataset_list()
                        print("[INFO] データセットリストのリフレッシュが完了しました")
                    else:
                        print("[WARNING] データセットリフレッシュ機能が見つかりません")
                except NameError:
                    print("[WARNING] edit_tabが定義されていません")
            # データエントリータブ（インデックス2）が選択された場合
            elif index == 2:  # データエントリータブ
                print("[INFO] データエントリータブが選択されました")
                # 最小版にはリフレッシュ機能がないため、現在はスキップ
                pass
        except Exception as e:
            print(f"[ERROR] タブ切り替え時のリフレッシュ処理でエラー: {e}")
    
    tab_widget.currentChanged.connect(on_tab_changed)
    
    main_layout.addWidget(tab_widget)
    main_widget.setLayout(main_layout)
    
    return main_widget


def create_original_dataset_open_widget(parent, title, color, create_auto_resize_button):
    """元のデータセット開設ウィジェット（後方互換性のため）"""
    # create_group_select_widgetをラップ
    try:
        result = create_group_select_widget(parent)
        if result and len(result) >= 1:
            return result[0]  # containerウィジェットを返す（新しい戻り値形式でも最初の要素はcontainer）
        else:
            # フォールバック
            widget = QWidget()
            layout = QVBoxLayout()
            layout.addWidget(QLabel("データセット開設機能を読み込み中..."))
            widget.setLayout(layout)
            return widget
    except Exception as e:
        print(f"[ERROR] データセット開設ウィジェットの作成に失敗: {e}")
        # エラー時は空のウィジェット
        widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"データセット開設機能の読み込みに失敗しました: {e}"))
        widget.setLayout(layout)
        return widget
