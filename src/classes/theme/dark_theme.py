"""
ダークテーマ定義 - ARIM RDE Tool v2.4.12

Material Design Dark準拠のダークモード配色。
高コントラスト・視認性重視の配色設計。
"""

from .theme_keys import ThemeKey


class DarkTheme:
    """ダークテーマ配色定義
    
    Material Design Dark Theme準拠。
    背景: #121212ベース + Elevation明度調整。
    テキスト: 87%/60%/38%白でコントラスト確保。
    """
    
    # テーマ名
    NAME = "Dark"
    
    # 色定義辞書
    COLORS = {
        # ========================================
        # Window - ウィンドウ・メイン背景
        # ========================================
        ThemeKey.WINDOW_BACKGROUND: "#121212",  # Material Dark背景
        ThemeKey.WINDOW_FOREGROUND: "#e0e0e0",  # 87%白相当
        
        # ========================================
        # Panel - パネル・グループボックス
        # ========================================
        ThemeKey.PANEL_BACKGROUND: "#1e1e1e",  # Elevation 1
        ThemeKey.PANEL_BORDER: "#333333",
        
        # 情報パネル（暗青）
        ThemeKey.PANEL_INFO_BACKGROUND: "#1e2a3a",
        ThemeKey.PANEL_INFO_TEXT: "#90caf9",  # Blue 200
        ThemeKey.PANEL_INFO_BORDER: "#64b5f6",  # Blue 300
        
        # 警告パネル（暗黄）
        ThemeKey.PANEL_WARNING_BACKGROUND: "#3a2e1e",
        ThemeKey.PANEL_WARNING_TEXT: "#ffb74d",  # Orange 300
        ThemeKey.PANEL_WARNING_BORDER: "#ffa726",  # Orange 400
        
        # 成功パネル（暗緑）
        ThemeKey.PANEL_SUCCESS_BACKGROUND: "#1e3a1e",
        ThemeKey.PANEL_SUCCESS_TEXT: "#81c784",  # Green 300
        ThemeKey.PANEL_SUCCESS_BORDER: "#66bb6a",  # Green 400
        
        # 中立パネル（灰色）
        ThemeKey.PANEL_NEUTRAL_BACKGROUND: "#2a2a2a",
        ThemeKey.PANEL_NEUTRAL_TEXT: "#b0b0b0",
        
        # メニューエリア（左側メニュー - 暗色）
        ThemeKey.MENU_BACKGROUND: "#1a1a1a",  # 非常に暗い背景
        ThemeKey.MENU_BUTTON_INACTIVE_BACKGROUND: "#2a2a2a",  # やや明るめ
        ThemeKey.MENU_BUTTON_INACTIVE_TEXT: "#b0b0b0",
        ThemeKey.MENU_BUTTON_ACTIVE_BACKGROUND: "#42a5f5",  # Primary Blue (Dark Mode)
        ThemeKey.MENU_BUTTON_ACTIVE_TEXT: "#000000",
        ThemeKey.MENU_BUTTON_HOVER_BACKGROUND: "#2a3a4a",  # Slightly lighter dark blue
        ThemeKey.MENU_BUTTON_HOVER_TEXT: "#64b5f6",
        
        # ========================================
        # Button - ボタン全般（明度を上げる）
        # ========================================
        
        # プライマリボタン（Blue 400→300→200）
        ThemeKey.BUTTON_PRIMARY_BACKGROUND: "#42a5f5",  # Blue 400
        ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER: "#64b5f6",  # Blue 300
        ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED: "#90caf9",  # Blue 200
        ThemeKey.BUTTON_PRIMARY_TEXT: "#000000",  # 暗背景には黒文字
        ThemeKey.BUTTON_PRIMARY_BORDER: "#64b5f6",
        
        # サクセスボタン（Green 400→300→200）
        ThemeKey.BUTTON_SUCCESS_BACKGROUND: "#66bb6a",  # Green 400
        ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER: "#81c784",  # Green 300
        ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED: "#a5d6a7",  # Green 200
        ThemeKey.BUTTON_SUCCESS_TEXT: "#000000",
        ThemeKey.BUTTON_SUCCESS_BORDER: "#81c784",
        
        # ワーニングボタン（Orange 400→300→200）
        ThemeKey.BUTTON_WARNING_BACKGROUND: "#ffa726",  # Orange 400
        ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER: "#ffcc80",  # Orange 200 - much lighter for visibility
        ThemeKey.BUTTON_WARNING_BACKGROUND_PRESSED: "#ffcc80",  # Orange 200
        ThemeKey.BUTTON_WARNING_TEXT: "#000000",
        ThemeKey.BUTTON_WARNING_BORDER: "#ffb74d",
        
        # デンジャーボタン（Red 400→300→200）
        ThemeKey.BUTTON_DANGER_BACKGROUND: "#ef5350",  # Red 400
        ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER: "#e57373",  # Red 300
        ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED: "#ef9a9a",  # Red 200
        ThemeKey.BUTTON_DANGER_TEXT: "#000000",
        ThemeKey.BUTTON_DANGER_BORDER: "#e57373",
        
        # セカンダリボタン（Purple 300→200）
        ThemeKey.BUTTON_SECONDARY_BACKGROUND: "#ba68c8",  # Purple 300
        ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER: "#ce93d8",  # Purple 200
        ThemeKey.BUTTON_SECONDARY_TEXT: "#000000",
        ThemeKey.BUTTON_SECONDARY_BORDER: "#ce93d8",
        
        # ニュートラルボタン（Grey 700→600）
        ThemeKey.BUTTON_NEUTRAL_BACKGROUND: "#616161",  # Grey 700
        ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER: "#757575",  # Grey 600
        ThemeKey.BUTTON_NEUTRAL_TEXT: "#ffffff",
        ThemeKey.BUTTON_NEUTRAL_BORDER: "#757575",
        
        # インフォボタン（Blue 400→300）
        ThemeKey.BUTTON_INFO_BACKGROUND: "#42a5f5",  # Blue 400
        ThemeKey.BUTTON_INFO_BACKGROUND_HOVER: "#90caf9",  # Blue 200 - much lighter for visibility
        ThemeKey.BUTTON_INFO_BACKGROUND_PRESSED: "#90caf9",  # Same as hover for pressed state
        ThemeKey.BUTTON_INFO_TEXT: "#000000",
        ThemeKey.BUTTON_INFO_BORDER: "#64b5f6",
        
        # 無効ボタン
        ThemeKey.BUTTON_DISABLED_BACKGROUND: "#2a2a2a",
        ThemeKey.BUTTON_DISABLED_TEXT: "#555555",
        ThemeKey.BUTTON_DISABLED_BORDER: "#333333",
        
        # デフォルトボタン（メニューボタン非アクティブ背景と揃える）
        ThemeKey.BUTTON_DEFAULT_BACKGROUND: "#2a2a2a",
        ThemeKey.BUTTON_DEFAULT_BACKGROUND_HOVER: "#333333",
        ThemeKey.BUTTON_DEFAULT_TEXT: "#e0e0e0",
        ThemeKey.BUTTON_DEFAULT_BORDER: "#333333",
        
        # 拡大表示ボタン（特殊）
        ThemeKey.BUTTON_EXPAND_BACKGROUND: "#1e3a5a",
        ThemeKey.BUTTON_EXPAND_BACKGROUND_HOVER: "#2a4a6a",
        ThemeKey.BUTTON_EXPAND_BACKGROUND_PRESSED: "#3a5a7a",
        ThemeKey.BUTTON_EXPAND_TEXT: "#64b5f6",
        ThemeKey.BUTTON_EXPAND_BORDER: "#42a5f5",
        
        # 特殊用途ボタン
        ThemeKey.BUTTON_API_BACKGROUND: "#1976d2",  # 少し明るく
        ThemeKey.BUTTON_API_BACKGROUND_HOVER: "#2196f3",
        ThemeKey.BUTTON_API_TEXT: "#ffffff",
        ThemeKey.BUTTON_API_BORDER: "#2196f3",
        
        ThemeKey.BUTTON_WEB_BACKGROUND: "#26a69a",  # Teal 400
        ThemeKey.BUTTON_WEB_BACKGROUND_HOVER: "#4db6ac",  # Teal 300
        ThemeKey.BUTTON_WEB_TEXT: "#000000",
        ThemeKey.BUTTON_WEB_BORDER: "#4db6ac",
        
        ThemeKey.BUTTON_AUTH_BACKGROUND: "#8d6e63",  # Brown 300
        ThemeKey.BUTTON_AUTH_BACKGROUND_HOVER: "#a1887f",  # Brown 200
        ThemeKey.BUTTON_AUTH_TEXT: "#000000",
        ThemeKey.BUTTON_AUTH_BORDER: "#a1887f",

        # BlueGreyボタン（暗色向けに明度を上げる）
        ThemeKey.BUTTON_BLUEGREY_BACKGROUND: "#78909c",  # BlueGrey 400
        ThemeKey.BUTTON_BLUEGREY_BACKGROUND_HOVER: "#90a4ae",  # 300
        ThemeKey.BUTTON_BLUEGREY_BACKGROUND_PRESSED: "#b0bec5",  # 200
        ThemeKey.BUTTON_BLUEGREY_TEXT: "#000000",
        ThemeKey.BUTTON_BLUEGREY_BORDER: "#90a4ae",
        
        # ========================================
        # Text - テキスト・ラベル（Material Dark準拠）
        # ========================================
        ThemeKey.TEXT_PRIMARY: "#e0e0e0",  # 87%白
        ThemeKey.TEXT_SECONDARY: "#b0b0b0",  # 60%白
        ThemeKey.TEXT_MUTED: "#808080",  # 38%白
        ThemeKey.TEXT_DISABLED: "#555555",
        ThemeKey.TEXT_PLACEHOLDER: "#9e9e9e",  # 明度UP（WCAG 4.8:1達成）
        
        # 状態別テキスト
        ThemeKey.TEXT_ERROR: "#ef5350",  # Red 400
        ThemeKey.TEXT_SUCCESS: "#66bb6a",  # Green 400
        ThemeKey.TEXT_WARNING: "#ffa726",  # Orange 400
        ThemeKey.TEXT_INFO: "#42a5f5",  # Blue 400
        
        # リンク
        ThemeKey.TEXT_LINK: "#64b5f6",  # Blue 300
        ThemeKey.TEXT_LINK_HOVER: "#90caf9",  # Blue 200
        
        # ========================================
        # Input - 入力フィールド
        # ========================================
        ThemeKey.INPUT_BACKGROUND: "#161616",  # WINDOWより+4明度（境界差別化）
        ThemeKey.INPUT_BORDER: "#444444",
        ThemeKey.INPUT_TEXT: "#e0e0e0",
        # プレースホルダ: 通常時は寒色系（既存テーマのシアン/Teal系）、無効時は灰色系
        ThemeKey.INPUT_PLACEHOLDER: "#4db6ac",  # Teal 300 (BUTTON_WEB_BACKGROUND_HOVER)
        ThemeKey.INPUT_PLACEHOLDER_DISABLED: "#9e9e9e",

        # TextArea（QTextEdit/QTextBrowser）
        # ダークではINPUTと同等で良い（差別化は主に枠線とタブ背景で担保）
        ThemeKey.TEXT_AREA_BACKGROUND: "#161616",
        ThemeKey.TEXT_AREA_BACKGROUND_FOCUS: "#181818",
        ThemeKey.TEXT_AREA_BACKGROUND_DISABLED: "#1e1e1e",

        # 無効テキストエリアの文字色はコントラスト優先（入力の無効よりは読みやすく）
        ThemeKey.TEXT_AREA_TEXT_DISABLED: "#b0b0b0",

        # 枠線太さ（QSS向け）
        ThemeKey.INPUT_BORDER_WIDTH: "1px",
        
        # フォーカス状態
        ThemeKey.INPUT_BACKGROUND_FOCUS: "#181818",  # +6明度（フォーカス時微明）
        ThemeKey.INPUT_BORDER_FOCUS: "#42a5f5",

        # フォーカス時枠線太さ（QSS向け）
        ThemeKey.INPUT_BORDER_FOCUS_WIDTH: "3px",
        
        # 無効状態
        ThemeKey.INPUT_BACKGROUND_DISABLED: "#1e1e1e",
        ThemeKey.INPUT_TEXT_DISABLED: "#666666",
        ThemeKey.INPUT_BORDER_DISABLED: "#333333",
        
        # ========================================
        # Border - 境界線・セパレーター
        # ========================================
        ThemeKey.BORDER_DEFAULT: "#333333",
        ThemeKey.BORDER_LIGHT: "#444444",
        ThemeKey.BORDER_DARK: "#222222",
        ThemeKey.BORDER_INFO: "#42a5f5",  # 情報パネル用（明るい青）
        ThemeKey.SEPARATOR_DEFAULT: "#333333",
        
        # ========================================
        # Table - テーブル・リスト
        # ========================================
        ThemeKey.TABLE_BACKGROUND: "#151515",  # +3明度（WINDOW背景と差別化）
        ThemeKey.TABLE_BORDER: "#333333",
        
        # ヘッダー
        ThemeKey.TABLE_HEADER_BACKGROUND: "#242424",  # やや暗く
        ThemeKey.TABLE_HEADER_TEXT: "#b0b0b0",
        
        ThemeKey.TABLE_HEADER_BORDER: "#333333",
        
        # 行
        ThemeKey.TABLE_ROW_BACKGROUND: "#141414",  # TABLE背景より微暗
        ThemeKey.TABLE_ROW_TEXT: "#e0e0e0",  # 明るいテキスト
        ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE: "#181818",  # +4明度（交互行）
        ThemeKey.TABLE_ROW_BACKGROUND_HOVER: "#242424",  # +10明度（ホバー）
        ThemeKey.TABLE_ROW_BACKGROUND_SELECTED: "#1e3a5a",
        ThemeKey.TABLE_ROW_TEXT_SELECTED: "#64b5f6",
        
        # サブグループ専用行背景（暗色調整）
        ThemeKey.TABLE_ROW_OWNER_BACKGROUND: "#1e2a4a",
        ThemeKey.TABLE_ROW_ASSISTANT_BACKGROUND: "#252a3a",
        ThemeKey.TABLE_ROW_MEMBER_BACKGROUND: "#1e3a1e",
        ThemeKey.TABLE_ROW_AGENT_BACKGROUND: "#3a3a1e",
        ThemeKey.TABLE_ROW_VIEWER_BACKGROUND: "#2a2a2a",
        
        # ========================================
        # Role - ロール別背景色（メンバーセレクター用・暗色調整）
        # ========================================
        ThemeKey.ROLE_OWNER_BACKGROUND: "#1e2a4a",  # より濃い青色（暗色）
        ThemeKey.ROLE_ASSISTANT_BACKGROUND: "#252a3a",  # 薄い青色（暗色）
        ThemeKey.ROLE_MEMBER_BACKGROUND: "#1e3a1e",  # 薄い緑色（暗色）
        ThemeKey.ROLE_AGENT_BACKGROUND: "#3a3a1e",  # 薄い黄色（暗色）
        ThemeKey.ROLE_VIEWER_BACKGROUND: "#2a2a2a",  # 薄い灰色（暗色）
        # ロール別テキスト色（暗色で視認性を確保）
        ThemeKey.ROLE_OWNER_TEXT: "#d2a679",
        ThemeKey.ROLE_ASSISTANT_TEXT: "#90caf9",
        ThemeKey.ROLE_MEMBER_TEXT: "#81c784",
        ThemeKey.ROLE_AGENT_TEXT: "#b39ddb",
        ThemeKey.ROLE_VIEWER_TEXT: "#90a4ae",
        
        # ========================================
        # Tab - タブUI
        # ========================================
        ThemeKey.TAB_BACKGROUND: "#1e1e1e",
        ThemeKey.TAB_BORDER: "#333333",
        ThemeKey.TAB_ACTIVE_BACKGROUND: "#2a2a2a",
        ThemeKey.TAB_ACTIVE_TEXT: "#64b5f6",
        ThemeKey.TAB_ACTIVE_BORDER: "#42a5f5",
        ThemeKey.TAB_INACTIVE_BACKGROUND: "#1e1e1e",
        ThemeKey.TAB_INACTIVE_TEXT: "#808080",
        
        # ========================================
        # Menu - メニュー・ナビゲーション
        # ========================================
        ThemeKey.MENU_BACKGROUND: "#1a1a1a",
        ThemeKey.MENU_BUTTON_INACTIVE_BACKGROUND: "#2a2a2a",
        ThemeKey.MENU_BUTTON_INACTIVE_TEXT: "#b0b0b0",
        ThemeKey.MENU_ITEM_BACKGROUND_HOVER: "#2a3a4a",
        
        # ========================================
        # Notification - 通知・バナー
        # ========================================
        
        # 情報通知（暗青）
        ThemeKey.NOTIFICATION_INFO_BACKGROUND: "#1e3a5a",
        ThemeKey.NOTIFICATION_INFO_TEXT: "#90caf9",
        ThemeKey.NOTIFICATION_INFO_BORDER: "#64b5f6",
        
        # 成功通知（暗緑）
        ThemeKey.NOTIFICATION_SUCCESS_BACKGROUND: "#1e3a1e",
        ThemeKey.NOTIFICATION_SUCCESS_TEXT: "#81c784",
        ThemeKey.NOTIFICATION_SUCCESS_BORDER: "#66bb6a",
        
        # 警告通知（暗黄）
        ThemeKey.NOTIFICATION_WARNING_BACKGROUND: "#3a2e1e",
        ThemeKey.NOTIFICATION_WARNING_TEXT: "#ffb74d",
        ThemeKey.NOTIFICATION_WARNING_BORDER: "#ffa726",
        
        # エラー通知（暗赤）
        ThemeKey.NOTIFICATION_ERROR_BACKGROUND: "#3a1e1e",
        ThemeKey.NOTIFICATION_ERROR_TEXT: "#e57373",
        ThemeKey.NOTIFICATION_ERROR_BORDER: "#ef5350",
        
        # ========================================
        # ComboBox - コンボボックス
        # ========================================
        ThemeKey.COMBO_BACKGROUND: "#171717",  # +5明度（INPUTと差別化）
        ThemeKey.COMBO_BORDER: "#444444",
        ThemeKey.COMBO_BORDER_FOCUS: "#42a5f5",
        ThemeKey.COMBO_BACKGROUND_FOCUS: "#1e3a5a",
        ThemeKey.COMBO_ARROW_BACKGROUND: "#42a5f5",
        ThemeKey.COMBO_ARROW_BACKGROUND_PRESSED: "#64b5f6",
        ThemeKey.COMBO_DROPDOWN_BACKGROUND: "#171717",  # COMBO背景と統一
        ThemeKey.COMBO_DROPDOWN_BORDER: "#64b5f6",
        
        # ========================================
        # ScrollBar - スクロールバー
        # ========================================
        ThemeKey.SCROLLBAR_BACKGROUND: "#1e1e1e",
        ThemeKey.SCROLLBAR_HANDLE: "#555555",
        ThemeKey.SCROLLBAR_HANDLE_HOVER: "#666666",
        
        # ========================================
        # Status - ステータス表示
        # ========================================
        ThemeKey.STATUS_BACKGROUND: "#2a2a2a",
        ThemeKey.STATUS_BORDER: "#444444",
        ThemeKey.STATUS_TEXT: "#b0b0b0",
        ThemeKey.STATUS_SUCCESS: "#66bb6a",  # 成功状態（明るい緑）
        ThemeKey.STATUS_WARNING: "#ffa726",  # 警告状態（明るいオレンジ）
        ThemeKey.STATUS_ERROR: "#ef5350",  # エラー状態（明るい赤）
        
        # ========================================
        # GroupBox - グループボックス
        # ========================================
        ThemeKey.GROUPBOX_BACKGROUND: "#1e1e1e",
        ThemeKey.GROUPBOX_BORDER: "#42a5f5",
        ThemeKey.GROUPBOX_TITLE_TEXT: "#64b5f6",
        
        # ========================================
        # Overlay - オーバーレイ・モーダル
        # ========================================
        ThemeKey.OVERLAY_BACKGROUND: "rgba(0, 0, 0, 0.7)",
        ThemeKey.OVERLAY_TEXT: "rgba(255, 255, 255, 0.87)",
        
        # ========================================
        # Icon - アイコン
        # ========================================
        ThemeKey.ICON_PRIMARY: "#64b5f6",
        ThemeKey.ICON_SECONDARY: "#757575",
        ThemeKey.ICON_SUCCESS: "#66bb6a",
        ThemeKey.ICON_WARNING: "#ffa726",
        ThemeKey.ICON_DANGER: "#ef5350",
        
        # ========================================
        # Markdown - マークダウン表示
        # ========================================
        ThemeKey.MARKDOWN_H1_TEXT: "#90caf9",
        ThemeKey.MARKDOWN_H1_BORDER: "#64b5f6",
        ThemeKey.MARKDOWN_H2_TEXT: "#b0b0b0",
        ThemeKey.MARKDOWN_H2_BORDER: "#555555",
        ThemeKey.MARKDOWN_H3_TEXT: "#808080",
        ThemeKey.MARKDOWN_CODE_BACKGROUND: "#2a2a2a",
        ThemeKey.MARKDOWN_BLOCKQUOTE_BORDER: "#64b5f6",
        ThemeKey.MARKDOWN_BLOCKQUOTE_TEXT: "#808080",
        ThemeKey.MARKDOWN_LINK: "#64b5f6",
        
        # ========================================
        # Portal - データポータル専用
        # ========================================
        ThemeKey.PORTAL_DATASET_ROW_BACKGROUND: "#1e2a3a",
        ThemeKey.PORTAL_DATASET_ROW_BACKGROUND_HOVER: "#2a3a4a",
        ThemeKey.PORTAL_THUMBNAIL_BORDER: "#444444",
        ThemeKey.PORTAL_THUMBNAIL_BACKGROUND: "#2a2a2a",
        
        # ========================================
        # Data Entry - データ登録UI専用
        # ========================================
        # スクロールエリア
        ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND: "#1e1e1e",
        ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER: "#333333",
        
        # データ登録タブコンテナ
        ThemeKey.DATA_ENTRY_TAB_CONTAINER_BACKGROUND: "#1e1e1e",
        
        # ファイルツリー（一括登録）
        ThemeKey.FILE_TREE_BACKGROUND: "#151515",  # TABLE背景と統一
        ThemeKey.FILE_TREE_TEXT: "#e0e0e0",
        ThemeKey.FILE_TREE_BORDER: "#333333",
        ThemeKey.FILE_TREE_HEADER_BACKGROUND: "#242424",
        ThemeKey.FILE_TREE_HEADER_TEXT: "#b0b0b0",
        ThemeKey.FILE_TREE_ROW_ALTERNATE: "#181818",  # TABLE行交互色と統一
        ThemeKey.FILE_TREE_ROW_HOVER: "#242424",  # TABLEホバー色と統一
        ThemeKey.FILE_TREE_ROW_SELECTED: "#1e3a5a",
        
        # ファイルセットテーブル（一括登録）
        ThemeKey.FILESET_TABLE_BACKGROUND: "#151515",  # TABLE背景と統一
        ThemeKey.FILESET_TABLE_BORDER: "#333333",
        ThemeKey.FILESET_TABLE_HEADER_BACKGROUND: "#242424",
        ThemeKey.FILESET_TABLE_HEADER_TEXT: "#b0b0b0",
        ThemeKey.FILESET_TABLE_ROW_ALTERNATE: "#181818",  # TABLE行交互色と統一
        ThemeKey.FILESET_TABLE_ROW_HOVER: "#242424",  # TABLEホバー色と統一
        
        # プレビューダイアログ
        ThemeKey.PREVIEW_DIALOG_BACKGROUND: "#1e1e1e",
        ThemeKey.PREVIEW_DIALOG_TEXT: "#e0e0e0",
        ThemeKey.PREVIEW_DIALOG_BORDER: "#333333",
        
        # 情報表示ラベル
        ThemeKey.INFO_LABEL_BACKGROUND: "#1e2a3a",
        ThemeKey.INFO_LABEL_TEXT: "#90caf9",
        ThemeKey.INFO_LABEL_BORDER: "#64b5f6",
    }
    
    @classmethod
    def get_color(cls, key: ThemeKey) -> str:
        """指定されたキーの色を取得
        
        Args:
            key: テーマキー
            
        Returns:
            色文字列（#RRGGBB または rgba(...)）
            
        Raises:
            KeyError: キーが存在しない場合
        """
        if key not in cls.COLORS:
            raise KeyError(f"Color key '{key}' not found in {cls.NAME} theme")
        return cls.COLORS[key]
    
    @classmethod
    def get_all_colors(cls) -> dict[ThemeKey, str]:
        """すべての色定義を取得"""
        return cls.COLORS.copy()
    
    @classmethod
    def validate_completeness(cls) -> tuple[bool, list[ThemeKey]]:
        """色定義の完全性をチェック
        
        Returns:
            (完全かどうか, 未定義のキーリスト)
        """
        all_keys = set(ThemeKey)
        defined_keys = set(cls.COLORS.keys())
        missing_keys = all_keys - defined_keys
        return len(missing_keys) == 0, list(missing_keys)
