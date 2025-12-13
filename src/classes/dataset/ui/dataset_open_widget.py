"""
データセット開設・編集のタブ付きウィジェット

将来的な拡張:
    このウィジェットでもAI説明文提案機能を実装する場合は、
    AIDescriptionSuggestionDialog を mode="dataset_suggestion" で呼び出す。
    
    使用例:
        from classes.dataset.ui.ai_suggestion_dialog import AISuggestionDialog
        
        dialog = AISuggestionDialog(
            parent=self,
            context_data=context_data,
            auto_generate=True,
            mode="dataset_suggestion"  # データセット提案モード
        )
        
        if dialog.exec() == QDialog.Accepted:
            suggestion = dialog.get_selected_suggestion()
            # 説明文フィールドに反映
"""
import os
from qt_compat.widgets import QWidget, QVBoxLayout, QLabel, QTabWidget
from classes.dataset.core.dataset_open_logic import create_group_select_widget
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

import logging

# ロガー設定
logger = logging.getLogger(__name__)


def create_dataset_open_widget(parent, title, create_auto_resize_button):
    """データセット開設・編集のタブ付きウィジェット"""
    # メインコンテナ
    main_widget = QWidget()
    main_layout = QVBoxLayout()
    # タブ管理用のリファレンスを保持（クリーンアップや再生成時に使用）
    main_widget._dataset_tab_widget = None  # type: ignore[attr-defined]
    main_widget._dataset_create_tab = None  # type: ignore[attr-defined]
    main_widget._dataset_edit_tab = None  # type: ignore[attr-defined]
    main_widget._dataset_dataentry_tab = None  # type: ignore[attr-defined]
    
    # タイトル
    label = QLabel(f"{title}機能")
    label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {get_color(ThemeKey.TEXT_INFO)}; padding: 10px;")
    #main_layout.addWidget(label)
    
    # タブウィジェット
    tab_widget = QTabWidget()
    main_widget._dataset_tab_widget = tab_widget  # type: ignore[attr-defined]
    
    # 新規開設タブ
    try:
        create_tab_result = create_group_select_widget(parent)
        if create_tab_result and len(create_tab_result) >= 1:
            create_tab = create_tab_result[0]  # containerウィジェットを取得
            main_widget._dataset_create_tab = create_tab  # type: ignore[attr-defined]
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
        logger.warning("データセット開設タブの作成に失敗: %s", e)
        # エラー時は空のタブを作成
        from qt_compat.widgets import QLabel as ErrorLabel
        error_widget = QWidget()
        error_layout = QVBoxLayout()
        error_layout.addWidget(ErrorLabel(f"データセット開設機能の読み込みに失敗しました: {e}"))
        error_widget.setLayout(error_layout)
        tab_widget.addTab(error_widget, "新規開設")
    
    # 編集タブ
    edit_tab = None  # 初期化
    try:
        from classes.dataset.ui.dataset_edit_widget import create_dataset_edit_widget
        edit_tab = create_dataset_edit_widget(parent, "データセット編集", create_auto_resize_button)
        tab_widget.addTab(edit_tab, "修正")
        main_widget._dataset_edit_tab = edit_tab  # type: ignore[attr-defined]
        
    except Exception as e:
        logger.warning("データセット編集タブの作成に失敗: %s", e)
        # エラー時は新規開設のみ
    
    # データエントリータブ（最小版）
    try:
        from classes.dataset.ui.dataset_dataentry_widget_minimal import create_dataset_dataentry_widget
        dataentry_tab = create_dataset_dataentry_widget(parent, "データエントリー", create_auto_resize_button)
        dataentry_tab = create_dataset_dataentry_widget(parent, "データエントリー", create_auto_resize_button)
        tab_widget.addTab(dataentry_tab, "タイル（データエントリー）")
        main_widget._dataset_dataentry_tab = dataentry_tab  # type: ignore[attr-defined]
        
    except Exception as e:
        logger.warning("データエントリータブの作成に失敗: %s", e)
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
                logger.info("修正タブが選択されました - データセットリストをリフレッシュします")
                # edit_tab内のload_existing_datasets関数を呼び出し
                if edit_tab is not None and hasattr(edit_tab, '_refresh_dataset_list'):
                    edit_tab._refresh_dataset_list()
                    logger.info("データセットリストのリフレッシュが完了しました")
                else:
                    logger.debug("データセットリフレッシュ機能がスキップされました (edit_tab=%s)", edit_tab is not None)
            # データエントリータブ（インデックス2）が選択された場合
            elif index == 2:  # データエントリータブ
                logger.info("データエントリータブが選択されました")
                # 最小版にはリフレッシュ機能がないため、現在はスキップ
                pass
        except Exception as e:
            logger.error("タブ切り替え時のリフレッシュ処理でエラー: %s", e)
    
    tab_widget.currentChanged.connect(on_tab_changed)
    
    main_layout.addWidget(tab_widget)
    main_widget.setLayout(main_layout)
    
    return main_widget


def create_original_dataset_open_widget(parent, title, create_auto_resize_button):
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
        logger.error("データセット開設ウィジェットの作成に失敗: %s", e)
        # エラー時は空のウィジェット
        widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"データセット開設機能の読み込みに失敗しました: {e}"))
        widget.setLayout(layout)
        return widget
