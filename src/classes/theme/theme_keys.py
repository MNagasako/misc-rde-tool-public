"""
テーマキー定義 - ARIM RDE Tool v2.3.9

UI要素の色を参照するためのキー定義。
セマンティックな命名規則に基づく階層構造。

命名規則: <要素種別>.<用途>.<属性>.<状態>
例: button.primary.background.hover
"""

from enum import Enum


class ThemeKey(str, Enum):
    """テーマキー列挙型
    
    UI要素の色を参照するための文字列キー。
    Enum継承により、型安全性と補完機能を提供。
    """
    
    # ========================================
    # Window - ウィンドウ・メイン背景
    # ========================================
    WINDOW_BACKGROUND = "window.background"
    WINDOW_FOREGROUND = "window.foreground"
    
    # ========================================
    # Panel - パネル・グループボックス
    # ========================================
    PANEL_BACKGROUND = "panel.background"
    PANEL_BORDER = "panel.border"
    
    # 情報パネル（青系）
    PANEL_INFO_BACKGROUND = "panel.info.background"
    PANEL_INFO_TEXT = "panel.info.text"
    PANEL_INFO_BORDER = "panel.info.border"
    
    # 警告パネル（黄系）
    PANEL_WARNING_BACKGROUND = "panel.warning.background"
    PANEL_WARNING_TEXT = "panel.warning.text"
    PANEL_WARNING_BORDER = "panel.warning.border"
    
    # 成功パネル（緑系）
    PANEL_SUCCESS_BACKGROUND = "panel.success.background"
    PANEL_SUCCESS_TEXT = "panel.success.text"
    PANEL_SUCCESS_BORDER = "panel.success.border"
    
    # 中立パネル（灰色）
    PANEL_NEUTRAL_BACKGROUND = "panel.neutral.background"
    PANEL_NEUTRAL_TEXT = "panel.neutral.text"
    
    # メニューエリア（左側メニュー）
    MENU_BACKGROUND = "menu.background"
    MENU_BUTTON_INACTIVE_BACKGROUND = "menu.button.inactive.background"
    MENU_BUTTON_INACTIVE_TEXT = "menu.button.inactive.text"
    MENU_BUTTON_ACTIVE_BACKGROUND = "menu.button.active.background"
    MENU_BUTTON_ACTIVE_TEXT = "menu.button.active.text"
    MENU_BUTTON_HOVER_BACKGROUND = "menu.button.hover.background"
    MENU_BUTTON_HOVER_TEXT = "menu.button.hover.text"
    
    # ========================================
    # Button - ボタン全般
    # ========================================
    
    # プライマリボタン（青系 - メインアクション）
    BUTTON_PRIMARY_BACKGROUND = "button.primary.background"
    BUTTON_PRIMARY_BACKGROUND_HOVER = "button.primary.background.hover"
    BUTTON_PRIMARY_BACKGROUND_PRESSED = "button.primary.background.pressed"
    BUTTON_PRIMARY_TEXT = "button.primary.text"
    BUTTON_PRIMARY_BORDER = "button.primary.border"
    
    # サクセスボタン（緑系 - 成功・確認）
    BUTTON_SUCCESS_BACKGROUND = "button.success.background"
    BUTTON_SUCCESS_BACKGROUND_HOVER = "button.success.background.hover"
    BUTTON_SUCCESS_BACKGROUND_PRESSED = "button.success.background.pressed"
    BUTTON_SUCCESS_TEXT = "button.success.text"
    BUTTON_SUCCESS_BORDER = "button.success.border"
    
    # ワーニングボタン（橙系 - 警告）
    BUTTON_WARNING_BACKGROUND = "button.warning.background"
    BUTTON_WARNING_BACKGROUND_HOVER = "button.warning.background.hover"
    BUTTON_WARNING_BACKGROUND_PRESSED = "button.warning.background.pressed"
    BUTTON_WARNING_TEXT = "button.warning.text"
    BUTTON_WARNING_BORDER = "button.warning.border"
    
    # デンジャーボタン（赤系 - エラー・削除）
    BUTTON_DANGER_BACKGROUND = "button.danger.background"
    BUTTON_DANGER_BACKGROUND_HOVER = "button.danger.background.hover"
    BUTTON_DANGER_BACKGROUND_PRESSED = "button.danger.background.pressed"
    BUTTON_DANGER_TEXT = "button.danger.text"
    BUTTON_DANGER_BORDER = "button.danger.border"
    
    # セカンダリボタン（紫系 - 副次的機能）
    BUTTON_SECONDARY_BACKGROUND = "button.secondary.background"
    BUTTON_SECONDARY_BACKGROUND_HOVER = "button.secondary.background.hover"
    BUTTON_SECONDARY_TEXT = "button.secondary.text"
    BUTTON_SECONDARY_BORDER = "button.secondary.border"
    
    # ニュートラルボタン（灰色 - 非アクティブ）
    BUTTON_NEUTRAL_BACKGROUND = "button.neutral.background"
    BUTTON_NEUTRAL_BACKGROUND_HOVER = "button.neutral.background.hover"
    BUTTON_NEUTRAL_TEXT = "button.neutral.text"
    BUTTON_NEUTRAL_BORDER = "button.neutral.border"
    
    # インフォボタン（水色 - 情報）
    BUTTON_INFO_BACKGROUND = "button.info.background"
    BUTTON_INFO_BACKGROUND_HOVER = "button.info.background.hover"
    BUTTON_INFO_BACKGROUND_PRESSED = "button.info.background.pressed"
    BUTTON_INFO_TEXT = "button.info.text"
    BUTTON_INFO_BORDER = "button.info.border"
    
    # 無効ボタン
    BUTTON_DISABLED_BACKGROUND = "button.disabled.background"
    BUTTON_DISABLED_TEXT = "button.disabled.text"
    BUTTON_DISABLED_BORDER = "button.disabled.border"
    
    # デフォルトボタン（薄灰色）
    BUTTON_DEFAULT_BACKGROUND = "button.default.background"
    BUTTON_DEFAULT_BACKGROUND_HOVER = "button.default.background.hover"
    BUTTON_DEFAULT_TEXT = "button.default.text"
    BUTTON_DEFAULT_BORDER = "button.default.border"
    
    # 拡大表示ボタン（特殊）
    BUTTON_EXPAND_BACKGROUND = "button.expand.background"
    BUTTON_EXPAND_BACKGROUND_HOVER = "button.expand.background.hover"
    BUTTON_EXPAND_BACKGROUND_PRESSED = "button.expand.background.pressed"
    BUTTON_EXPAND_TEXT = "button.expand.text"
    BUTTON_EXPAND_BORDER = "button.expand.border"
    
    # 特殊用途ボタン
    BUTTON_API_BACKGROUND = "button.api.background"
    BUTTON_API_BACKGROUND_HOVER = "button.api.background.hover"
    BUTTON_API_TEXT = "button.api.text"
    BUTTON_API_BORDER = "button.api.border"
    
    BUTTON_WEB_BACKGROUND = "button.web.background"
    BUTTON_WEB_BACKGROUND_HOVER = "button.web.background.hover"
    BUTTON_WEB_TEXT = "button.web.text"
    BUTTON_WEB_BORDER = "button.web.border"
    
    BUTTON_AUTH_BACKGROUND = "button.auth.background"
    BUTTON_AUTH_BACKGROUND_HOVER = "button.auth.background.hover"
    BUTTON_AUTH_TEXT = "button.auth.text"
    BUTTON_AUTH_BORDER = "button.auth.border"

    # BlueGreyボタン（補助アクション・情報系）
    BUTTON_BLUEGREY_BACKGROUND = "button.bluegrey.background"
    BUTTON_BLUEGREY_BACKGROUND_HOVER = "button.bluegrey.background.hover"
    BUTTON_BLUEGREY_BACKGROUND_PRESSED = "button.bluegrey.background.pressed"
    BUTTON_BLUEGREY_TEXT = "button.bluegrey.text"
    BUTTON_BLUEGREY_BORDER = "button.bluegrey.border"
    
    # ========================================
    # Text - テキスト・ラベル
    # ========================================
    TEXT_PRIMARY = "text.primary"
    TEXT_SECONDARY = "text.secondary"
    TEXT_MUTED = "text.muted"
    TEXT_DISABLED = "text.disabled"
    TEXT_PLACEHOLDER = "text.placeholder"
    
    # 状態別テキスト
    TEXT_ERROR = "text.error"
    TEXT_SUCCESS = "text.success"
    TEXT_WARNING = "text.warning"
    TEXT_INFO = "text.info"
    
    # リンク
    TEXT_LINK = "text.link"
    TEXT_LINK_HOVER = "text.link.hover"
    
    # ========================================
    # Input - 入力フィールド
    # ========================================
    INPUT_BACKGROUND = "input.background"
    INPUT_BORDER = "input.border"
    INPUT_TEXT = "input.text"
    INPUT_PLACEHOLDER = "input.placeholder"
    INPUT_PLACEHOLDER_DISABLED = "input.placeholder.disabled"

    # TextArea - テキストエリア（QTextEdit/QTextBrowser）
    # QAbstractScrollArea系は環境によって QSS の ::viewport が効かない/揺れることがあるため、
    # グローバルQSSでは ::viewport に加えて QWidget#qt_scrollarea_viewport にも同一スタイルを適用する。
    # スタイル方針: docs/STYLING_AND_THEME_GUIDE.md
    TEXT_AREA_BACKGROUND = "text_area.background"
    TEXT_AREA_BACKGROUND_FOCUS = "text_area.background.focus"
    TEXT_AREA_BACKGROUND_DISABLED = "text_area.background.disabled"
    TEXT_AREA_TEXT_DISABLED = "text_area.text.disabled"

    # 枠線太さ（QSS向け。"1px" のような値を想定）
    INPUT_BORDER_WIDTH = "input.border.width"
    
    # フォーカス状態
    INPUT_BACKGROUND_FOCUS = "input.background.focus"
    INPUT_BORDER_FOCUS = "input.border.focus"

    # フォーカス時の枠線太さ（QSS向け。"2px" のような値を想定）
    INPUT_BORDER_FOCUS_WIDTH = "input.border.focus.width"
    
    # 無効状態
    INPUT_BACKGROUND_DISABLED = "input.background.disabled"
    INPUT_TEXT_DISABLED = "input.text.disabled"
    INPUT_BORDER_DISABLED = "input.border.disabled"
    
    # ========================================
    # Border - 境界線・セパレーター
    # ========================================
    BORDER_DEFAULT = "border.default"
    BORDER_LIGHT = "border.light"
    BORDER_DARK = "border.dark"
    BORDER_INFO = "border.info"  # 情報パネル用ボーダー
    SEPARATOR_DEFAULT = "separator.default"
    
    # ========================================
    # Table - テーブル・リスト
    # ========================================
    TABLE_BACKGROUND = "table.background"
    TABLE_BORDER = "table.border"
    
    # ヘッダー
    TABLE_HEADER_BACKGROUND = "table.header.background"
    TABLE_HEADER_TEXT = "table.header.text"
    TABLE_HEADER_BORDER = "table.header.border"
    
    # 行
    TABLE_ROW_BACKGROUND = "table.row.background"
    TABLE_ROW_TEXT = "table.row.text"
    TABLE_ROW_BACKGROUND_ALTERNATE = "table.row.background.alternate"
    TABLE_ROW_BACKGROUND_HOVER = "table.row.background.hover"
    TABLE_ROW_BACKGROUND_SELECTED = "table.row.background.selected"
    TABLE_ROW_TEXT_SELECTED = "table.row.text.selected"
    
    # サブグループ専用行背景
    TABLE_ROW_OWNER_BACKGROUND = "table.row.owner.background"
    TABLE_ROW_ASSISTANT_BACKGROUND = "table.row.assistant.background"
    TABLE_ROW_MEMBER_BACKGROUND = "table.row.member.background"
    TABLE_ROW_AGENT_BACKGROUND = "table.row.agent.background"
    TABLE_ROW_VIEWER_BACKGROUND = "table.row.viewer.background"
    
    # ========================================
    # Role - ロール別背景色（メンバーセレクター用）
    # ========================================
    ROLE_OWNER_BACKGROUND = "role.owner.background"
    ROLE_ASSISTANT_BACKGROUND = "role.assistant.background"
    ROLE_MEMBER_BACKGROUND = "role.member.background"
    ROLE_AGENT_BACKGROUND = "role.agent.background"
    ROLE_VIEWER_BACKGROUND = "role.viewer.background"
    # ロール別テキスト色
    ROLE_OWNER_TEXT = "role.owner.text"
    ROLE_ASSISTANT_TEXT = "role.assistant.text"
    ROLE_MEMBER_TEXT = "role.member.text"
    ROLE_AGENT_TEXT = "role.agent.text"
    ROLE_VIEWER_TEXT = "role.viewer.text"
    
    # ========================================
    # Tab - タブUI
    # ========================================
    TAB_BACKGROUND = "tab.background"
    TAB_BORDER = "tab.border"
    TAB_ACTIVE_BACKGROUND = "tab.active.background"
    TAB_ACTIVE_TEXT = "tab.active.text"
    TAB_ACTIVE_BORDER = "tab.active.border"
    TAB_INACTIVE_BACKGROUND = "tab.inactive.background"
    TAB_INACTIVE_TEXT = "tab.inactive.text"
    
    # ========================================
    # Menu - メニュー・ナビゲーション
    # ========================================
    # 注: MENU_BACKGROUND等は上部で既に定義済み（53-55行目）
    MENU_ITEM_BACKGROUND_HOVER = "menu.item.background.hover"
    
    # ========================================
    # Notification - 通知・バナー
    # ========================================
    
    # 情報通知（青）
    NOTIFICATION_INFO_BACKGROUND = "notification.info.background"
    NOTIFICATION_INFO_TEXT = "notification.info.text"
    NOTIFICATION_INFO_BORDER = "notification.info.border"
    
    # 成功通知（緑）
    NOTIFICATION_SUCCESS_BACKGROUND = "notification.success.background"
    NOTIFICATION_SUCCESS_TEXT = "notification.success.text"
    NOTIFICATION_SUCCESS_BORDER = "notification.success.border"
    
    # 警告通知（黄）
    NOTIFICATION_WARNING_BACKGROUND = "notification.warning.background"
    NOTIFICATION_WARNING_TEXT = "notification.warning.text"
    NOTIFICATION_WARNING_BORDER = "notification.warning.border"
    
    # エラー通知（赤）
    NOTIFICATION_ERROR_BACKGROUND = "notification.error.background"
    NOTIFICATION_ERROR_TEXT = "notification.error.text"
    NOTIFICATION_ERROR_BORDER = "notification.error.border"
    
    # ========================================
    # ComboBox - コンボボックス
    # ========================================
    COMBO_BACKGROUND = "combo.background"
    COMBO_BORDER = "combo.border"
    COMBO_BORDER_FOCUS = "combo.border.focus"
    COMBO_BACKGROUND_FOCUS = "combo.background.focus"
    COMBO_ARROW_BACKGROUND = "combo.arrow.background"
    COMBO_ARROW_BACKGROUND_PRESSED = "combo.arrow.background.pressed"
    COMBO_DROPDOWN_BACKGROUND = "combo.dropdown.background"
    COMBO_DROPDOWN_BORDER = "combo.dropdown.border"
    
    # ========================================
    # ScrollBar - スクロールバー
    # ========================================
    SCROLLBAR_BACKGROUND = "scrollbar.background"
    SCROLLBAR_HANDLE = "scrollbar.handle"
    SCROLLBAR_HANDLE_HOVER = "scrollbar.handle.hover"
    
    # ========================================
    # Status - ステータス表示
    # ========================================
    STATUS_BACKGROUND = "status.background"
    STATUS_BORDER = "status.border"
    STATUS_TEXT = "status.text"
    STATUS_SUCCESS = "status.success"  # 成功状態のテキスト色
    STATUS_WARNING = "status.warning"  # 警告状態のテキスト色
    STATUS_ERROR = "status.error"  # エラー状態のテキスト色
    
    # ========================================
    # GroupBox - グループボックス
    # ========================================
    GROUPBOX_BACKGROUND = "groupbox.background"
    GROUPBOX_BORDER = "groupbox.border"
    GROUPBOX_TITLE_TEXT = "groupbox.title.text"
    
    # ========================================
    # Overlay - オーバーレイ・モーダル
    # ========================================
    OVERLAY_BACKGROUND = "overlay.background"
    OVERLAY_TEXT = "overlay.text"
    
    # ========================================
    # Icon - アイコン
    # ========================================
    ICON_PRIMARY = "icon.primary"
    ICON_SECONDARY = "icon.secondary"
    ICON_SUCCESS = "icon.success"
    ICON_WARNING = "icon.warning"
    ICON_DANGER = "icon.danger"
    
    # ========================================
    # Markdown - マークダウン表示
    # ========================================
    MARKDOWN_H1_TEXT = "markdown.h1.text"
    MARKDOWN_H1_BORDER = "markdown.h1.border"
    MARKDOWN_H2_TEXT = "markdown.h2.text"
    MARKDOWN_H2_BORDER = "markdown.h2.border"
    MARKDOWN_H3_TEXT = "markdown.h3.text"
    MARKDOWN_CODE_BACKGROUND = "markdown.code.background"
    MARKDOWN_BLOCKQUOTE_BORDER = "markdown.blockquote.border"
    MARKDOWN_BLOCKQUOTE_TEXT = "markdown.blockquote.text"
    MARKDOWN_LINK = "markdown.link"
    
    # ========================================
    # Portal - データポータル専用
    # ========================================
    PORTAL_DATASET_ROW_BACKGROUND = "portal.dataset.row.background"
    PORTAL_DATASET_ROW_BACKGROUND_HOVER = "portal.dataset.row.background.hover"
    PORTAL_THUMBNAIL_BORDER = "portal.thumbnail.border"
    PORTAL_THUMBNAIL_BACKGROUND = "portal.thumbnail.background"
    
    # ========================================
    # Data Entry - データ登録UI専用
    # ========================================
    # スクロールエリア
    DATA_ENTRY_SCROLL_AREA_BACKGROUND = "data_entry.scroll_area.background"
    DATA_ENTRY_SCROLL_AREA_BORDER = "data_entry.scroll_area.border"
    
    # データ登録タブコンテナ
    DATA_ENTRY_TAB_CONTAINER_BACKGROUND = "data_entry.tab_container.background"
    
    # ファイルツリー（一括登録）
    FILE_TREE_BACKGROUND = "file_tree.background"
    FILE_TREE_TEXT = "file_tree.text"
    FILE_TREE_BORDER = "file_tree.border"
    FILE_TREE_HEADER_BACKGROUND = "file_tree.header.background"
    FILE_TREE_HEADER_TEXT = "file_tree.header.text"
    FILE_TREE_ROW_ALTERNATE = "file_tree.row.alternate"
    FILE_TREE_ROW_HOVER = "file_tree.row.hover"
    FILE_TREE_ROW_SELECTED = "file_tree.row.selected"
    
    # ファイルセットテーブル（一括登録）
    FILESET_TABLE_BACKGROUND = "fileset_table.background"
    FILESET_TABLE_BORDER = "fileset_table.border"
    FILESET_TABLE_HEADER_BACKGROUND = "fileset_table.header.background"
    FILESET_TABLE_HEADER_TEXT = "fileset_table.header.text"
    FILESET_TABLE_ROW_ALTERNATE = "fileset_table.row.alternate"
    FILESET_TABLE_ROW_HOVER = "fileset_table.row.hover"
    
    # プレビューダイアログ
    PREVIEW_DIALOG_BACKGROUND = "preview_dialog.background"
    PREVIEW_DIALOG_TEXT = "preview_dialog.text"
    PREVIEW_DIALOG_BORDER = "preview_dialog.border"
    
    # 情報表示ラベル
    INFO_LABEL_BACKGROUND = "info_label.background"
    INFO_LABEL_TEXT = "info_label.text"
    INFO_LABEL_BORDER = "info_label.border"
    
    
    def __str__(self) -> str:
        """文字列表現（キー値を返す）"""
        return self.value
    
    @classmethod
    def get_all_keys(cls) -> list[str]:
        """すべてのキーを取得"""
        return [key.value for key in cls]
    
    @classmethod
    def validate_key(cls, key: str) -> bool:
        """キーが有効かチェック"""
        return key in cls._value2member_map_
