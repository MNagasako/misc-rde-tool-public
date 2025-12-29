"""
ライトテーマ定義 - ARIM RDE Tool v2.3.12

Material Design準拠のライトモード配色。
現行アプリの配色を忠実に再現。
"""

from .theme_keys import ThemeKey


class LightTheme:
    """ライトテーマ配色定義
    
    Material Design準拠の明るい配色。
    既存のライトモードUIを忠実に再現。
    
    """
    
    # テーマ名
    NAME = "Light"
    
    # 色定義辞書
    COLORS = {
        # ========================================
        # Window - ウィンドウ・メイン背景
        # ========================================
        ThemeKey.WINDOW_BACKGROUND: "#ffffff",
        ThemeKey.WINDOW_FOREGROUND: "#212529",
        
        # ========================================
        # Panel - パネル・グループボックス
        # ========================================
        ThemeKey.PANEL_BACKGROUND: "#f5f5f5",
        ThemeKey.PANEL_BORDER: "#ddd",
        
        # 情報パネル（青系）
        ThemeKey.PANEL_INFO_BACKGROUND: "#e3f2fd",
        ThemeKey.PANEL_INFO_TEXT: "#1976d2",
        ThemeKey.PANEL_INFO_BORDER: "#1976d2",
        
        # 警告パネル（黄系）
        ThemeKey.PANEL_WARNING_BACKGROUND: "#fff3cd",
        ThemeKey.PANEL_WARNING_TEXT: "#856404",
        ThemeKey.PANEL_WARNING_BORDER: "#ffc107",
        
        # 成功パネル（緑系）
        ThemeKey.PANEL_SUCCESS_BACKGROUND: "#e8f5e9",
        ThemeKey.PANEL_SUCCESS_TEXT: "#2e7d32",
        ThemeKey.PANEL_SUCCESS_BORDER: "#4caf50",
        
        # 中立パネル（灰色）
        ThemeKey.PANEL_NEUTRAL_BACKGROUND: "#f5f5f5",
        ThemeKey.PANEL_NEUTRAL_TEXT: "#616161",
        
        # メニューエリア（左側メニュー）
        ThemeKey.MENU_BACKGROUND: "#e3f2fd",  # ライトブルー背景
        ThemeKey.MENU_BUTTON_INACTIVE_BACKGROUND: "#90a4ae",  # Blue Grey 300
        ThemeKey.MENU_BUTTON_INACTIVE_TEXT: "#ffffff",
        ThemeKey.MENU_BUTTON_ACTIVE_BACKGROUND: "#1976d2",  # Primary Blue
        ThemeKey.MENU_BUTTON_ACTIVE_TEXT: "#ffffff",
        ThemeKey.MENU_BUTTON_HOVER_BACKGROUND: "#bbdefb",  # Lighter Blue
        ThemeKey.MENU_BUTTON_HOVER_TEXT: "#1976d2",
        
        # ========================================
        # Button - ボタン全般
        # ========================================
        
        # プライマリボタン（青系）
        ThemeKey.BUTTON_PRIMARY_BACKGROUND: "#1976d2",
        ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER: "#1565c0",
        ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED: "#0d47a1",
        ThemeKey.BUTTON_PRIMARY_TEXT: "#ffffff",
        ThemeKey.BUTTON_PRIMARY_BORDER: "#1565c0",
        
        # サクセスボタン（緑系）
        ThemeKey.BUTTON_SUCCESS_BACKGROUND: "#4CAF50",
        ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER: "#45a049",
        ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED: "#2E7D32",
        ThemeKey.BUTTON_SUCCESS_TEXT: "#ffffff",
        ThemeKey.BUTTON_SUCCESS_BORDER: "#45a049",
        
        # ワーニングボタン（橙系）
        ThemeKey.BUTTON_WARNING_BACKGROUND: "#FF9800",
        ThemeKey.BUTTON_WARNING_BACKGROUND_HOVER: "#E65100",  # Much darker for visibility
        ThemeKey.BUTTON_WARNING_BACKGROUND_PRESSED: "#e68900",
        ThemeKey.BUTTON_WARNING_TEXT: "#ffffff",
        ThemeKey.BUTTON_WARNING_BORDER: "#F57C00",
        
        # デンジャーボタン（赤系）
        ThemeKey.BUTTON_DANGER_BACKGROUND: "#F44336",
        ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER: "#D32F2F",
        ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED: "#da190b",
        ThemeKey.BUTTON_DANGER_TEXT: "#ffffff",
        ThemeKey.BUTTON_DANGER_BORDER: "#D32F2F",
        
        # セカンダリボタン（紫系）
        ThemeKey.BUTTON_SECONDARY_BACKGROUND: "#9C27B0",
        ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER: "#7B1FA2",
        ThemeKey.BUTTON_SECONDARY_TEXT: "#ffffff",
        ThemeKey.BUTTON_SECONDARY_BORDER: "#7B1FA2",
        
        # ニュートラルボタン（灰色）
        ThemeKey.BUTTON_NEUTRAL_BACKGROUND: "#757575",
        ThemeKey.BUTTON_NEUTRAL_BACKGROUND_HOVER: "#616161",
        ThemeKey.BUTTON_NEUTRAL_TEXT: "#ffffff",
        ThemeKey.BUTTON_NEUTRAL_BORDER: "#616161",
        
        # インフォボタン（水色）
        ThemeKey.BUTTON_INFO_BACKGROUND: "#2196F3",
        ThemeKey.BUTTON_INFO_BACKGROUND_HOVER: "#0d47a1",  # Much darker for visibility
        ThemeKey.BUTTON_INFO_BACKGROUND_PRESSED: "#0d47a1",  # Same as hover for pressed state
        ThemeKey.BUTTON_INFO_TEXT: "#ffffff",
        ThemeKey.BUTTON_INFO_BORDER: "#1976D2",
        
        # 無効ボタン
        ThemeKey.BUTTON_DISABLED_BACKGROUND: "#85929E",
        ThemeKey.BUTTON_DISABLED_TEXT: "#D5DBDB",
        ThemeKey.BUTTON_DISABLED_BORDER: "#5D6D7E",
        
        # デフォルトボタン（薄灰色）
        ThemeKey.BUTTON_DEFAULT_BACKGROUND: "#f5f5f5",
        ThemeKey.BUTTON_DEFAULT_BACKGROUND_HOVER: "#e0e0e0",
        ThemeKey.BUTTON_DEFAULT_TEXT: "#333333",
        ThemeKey.BUTTON_DEFAULT_BORDER: "#bbbbbb",
        
        # 拡大表示ボタン（特殊）
        ThemeKey.BUTTON_EXPAND_BACKGROUND: "#e3f2fd",
        ThemeKey.BUTTON_EXPAND_BACKGROUND_HOVER: "#bbdefb",
        ThemeKey.BUTTON_EXPAND_BACKGROUND_PRESSED: "#90caf9",
        ThemeKey.BUTTON_EXPAND_TEXT: "#1976d2",
        ThemeKey.BUTTON_EXPAND_BORDER: "#2196f3",
        
        # 特殊用途ボタン
        ThemeKey.BUTTON_API_BACKGROUND: "#0D47A1",
        ThemeKey.BUTTON_API_BACKGROUND_HOVER: "#1565C0",
        ThemeKey.BUTTON_API_TEXT: "#ffffff",
        ThemeKey.BUTTON_API_BORDER: "#1565C0",
        
        ThemeKey.BUTTON_WEB_BACKGROUND: "#009688",
        ThemeKey.BUTTON_WEB_BACKGROUND_HOVER: "#00796B",
        ThemeKey.BUTTON_WEB_TEXT: "#ffffff",
        ThemeKey.BUTTON_WEB_BORDER: "#00796B",
        
        ThemeKey.BUTTON_AUTH_BACKGROUND: "#795548",
        ThemeKey.BUTTON_AUTH_BACKGROUND_HOVER: "#5D4037",
        ThemeKey.BUTTON_AUTH_TEXT: "#ffffff",
        ThemeKey.BUTTON_AUTH_BORDER: "#5D4037",

        # BlueGreyボタン（補助情報系）
        ThemeKey.BUTTON_BLUEGREY_BACKGROUND: "#607d8b",
        ThemeKey.BUTTON_BLUEGREY_BACKGROUND_HOVER: "#546e7a",
        ThemeKey.BUTTON_BLUEGREY_BACKGROUND_PRESSED: "#455a64",
        ThemeKey.BUTTON_BLUEGREY_TEXT: "#ffffff",
        ThemeKey.BUTTON_BLUEGREY_BORDER: "#546e7a",
        
        # ========================================
        # Text - テキスト・ラベル
        # ========================================
        ThemeKey.TEXT_PRIMARY: "#212529",
        ThemeKey.TEXT_SECONDARY: "#495057",
        ThemeKey.TEXT_MUTED: "#666666",
        ThemeKey.TEXT_DISABLED: "#b0bec5",
        ThemeKey.TEXT_PLACEHOLDER: "#6c757d",  # 緑色から灰色へ変更（WCAG 5.5:1達成）
        
        # 状態別テキスト
        ThemeKey.TEXT_ERROR: "#d32f2f",
        ThemeKey.TEXT_SUCCESS: "#2e7d32",
        ThemeKey.TEXT_WARNING: "#e65100",
        ThemeKey.TEXT_INFO: "#1976d2",
        
        # リンク
        ThemeKey.TEXT_LINK: "#2196f3",
        ThemeKey.TEXT_LINK_HOVER: "#1976d2",
        
        # ========================================
        # Input - 入力フィールド
        # ========================================
        ThemeKey.INPUT_BACKGROUND: "#f8f9fa",  # 微灰色（WINDOW背景と差別化）
        ThemeKey.INPUT_BORDER: "#1C1D1F",
        ThemeKey.INPUT_TEXT: "#212529",
        # プレースホルダ: 通常時は寒色系（既存テーマのシアン/Teal系）、無効時は灰色系
        ThemeKey.INPUT_PLACEHOLDER: "#009688",  # Teal 500 (BUTTON_WEB_BACKGROUND)
        ThemeKey.INPUT_PLACEHOLDER_DISABLED: "#6c757d",
        # TextArea（QTextEdit/QTextBrowser）
        # 背景同化を避けるため、周囲のパネル背景より明確に明るくする
        ThemeKey.TEXT_AREA_BACKGROUND: "#ffffff",
        ThemeKey.TEXT_AREA_BACKGROUND_FOCUS: "#ffffff",
        ThemeKey.TEXT_AREA_BACKGROUND_DISABLED: "#f5f5f5",
        # 無効テキストエリアの文字色はコントラスト優先（入力の無効よりは読みやすく）
        ThemeKey.TEXT_AREA_TEXT_DISABLED: "#495057",

        # 枠線太さ（QSS向け）
        ThemeKey.INPUT_BORDER_WIDTH: "1px",
        
        # フォーカス状態
        ThemeKey.INPUT_BACKGROUND_FOCUS: "#ffffff",
        ThemeKey.INPUT_BORDER_FOCUS: "#2196f3",

        # フォーカス時枠線太さ（QSS向け）
        ThemeKey.INPUT_BORDER_FOCUS_WIDTH: "3px",
        
        # 無効状態
        ThemeKey.INPUT_BACKGROUND_DISABLED: "#f5f5f5",
        ThemeKey.INPUT_TEXT_DISABLED: "#666666",
        ThemeKey.INPUT_BORDER_DISABLED: "#cccccc",
        
        # ========================================
        # Border - 境界線・セパレーター
        # ========================================
        ThemeKey.BORDER_DEFAULT: "#dee2e6",
        ThemeKey.BORDER_LIGHT: "#e9ecef",
        ThemeKey.BORDER_DARK: "#adb5bd",
        ThemeKey.BORDER_INFO: "#1976d2",  # 情報パネル用（青）
        ThemeKey.SEPARATOR_DEFAULT: "#dee2e6",
        
        # ========================================
        # Table - テーブル・リスト
        # ========================================
        ThemeKey.TABLE_BACKGROUND: "#fdfdfd",  # オフホワイト（WINDOW背景と微差）
        ThemeKey.TABLE_BORDER: "#dee2e6",
        
        # ヘッダー
        ThemeKey.TABLE_HEADER_BACKGROUND: "#f8f9fa",
        ThemeKey.TABLE_HEADER_TEXT: "#495057",
        ThemeKey.TABLE_HEADER_BORDER: "#dee2e6",
        
        # 行
        ThemeKey.TABLE_ROW_BACKGROUND: "#fcfcfc",  # TABLE背景より微暗
        ThemeKey.TABLE_ROW_TEXT: "#212529",
        ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE: "#f8f9fa",
        ThemeKey.TABLE_ROW_BACKGROUND_HOVER: "#e9ecef",
        ThemeKey.TABLE_ROW_BACKGROUND_SELECTED: "#e3f2fd",
        ThemeKey.TABLE_ROW_TEXT_SELECTED: "#1976d2",
        
        # サブグループ専用行背景
        ThemeKey.TABLE_ROW_OWNER_BACKGROUND: "#c8dcff",
        ThemeKey.TABLE_ROW_ASSISTANT_BACKGROUND: "#e6f0ff",
        ThemeKey.TABLE_ROW_MEMBER_BACKGROUND: "#e6ffe6",
        ThemeKey.TABLE_ROW_AGENT_BACKGROUND: "#ffffe6",
        ThemeKey.TABLE_ROW_VIEWER_BACKGROUND: "#f0f0f0",
        
        # ========================================
        # Role - ロール別背景色（メンバーセレクター用）
        # ========================================
        ThemeKey.ROLE_OWNER_BACKGROUND: "#c8dcff",  # より濃い青色
        ThemeKey.ROLE_ASSISTANT_BACKGROUND: "#e6f0ff",  # 薄い青色
        ThemeKey.ROLE_MEMBER_BACKGROUND: "#e6ffe6",  # 薄い緑色
        ThemeKey.ROLE_AGENT_BACKGROUND: "#ffffe6",  # 薄い黄色
        ThemeKey.ROLE_VIEWER_BACKGROUND: "#f0f0f0",  # 薄い灰色
        # ロール別テキスト色（現行色を維持）
        ThemeKey.ROLE_OWNER_TEXT: "#B8860B",
        ThemeKey.ROLE_ASSISTANT_TEXT: "#4169E1",
        ThemeKey.ROLE_MEMBER_TEXT: "#228B22",
        ThemeKey.ROLE_AGENT_TEXT: "#9370DB",
        ThemeKey.ROLE_VIEWER_TEXT: "#607d8b",
        
        # ========================================
        # Tab - タブUI
        # ========================================
        ThemeKey.TAB_BACKGROUND: "#dadcdd",
        ThemeKey.TAB_BORDER: "#ddd",
        # タブ背景を少し暗くして、内部の入力エリアと区別しやすくする
        ThemeKey.TAB_ACTIVE_BACKGROUND: "#edf0f2",
        ThemeKey.TAB_ACTIVE_TEXT: "#2196f3",
        ThemeKey.TAB_ACTIVE_BORDER: "#2196f3",
        ThemeKey.TAB_INACTIVE_BACKGROUND: "#f8f9fa",
        ThemeKey.TAB_INACTIVE_TEXT: "#495057",
        
        # ========================================
        # Menu - メニュー・ナビゲーション
        # ========================================
        ThemeKey.MENU_BACKGROUND: "#e3f2fd",
        ThemeKey.MENU_BUTTON_INACTIVE_BACKGROUND: "#90a4ae",
        ThemeKey.MENU_BUTTON_INACTIVE_TEXT: "#ffffff",
        ThemeKey.MENU_ITEM_BACKGROUND_HOVER: "#bbdefb",
        
        # ========================================
        # Notification - 通知・バナー
        # ========================================
        
        # 情報通知（青）
        ThemeKey.NOTIFICATION_INFO_BACKGROUND: "#e3f2fd",
        ThemeKey.NOTIFICATION_INFO_TEXT: "#1976d2",
        ThemeKey.NOTIFICATION_INFO_BORDER: "#1976d2",
        
        # 成功通知（緑）
        ThemeKey.NOTIFICATION_SUCCESS_BACKGROUND: "#e8f5e9",
        ThemeKey.NOTIFICATION_SUCCESS_TEXT: "#2e7d32",
        ThemeKey.NOTIFICATION_SUCCESS_BORDER: "#4caf50",
        
        # 警告通知（黄）
        ThemeKey.NOTIFICATION_WARNING_BACKGROUND: "#fff3cd",
        ThemeKey.NOTIFICATION_WARNING_TEXT: "#856404",
        ThemeKey.NOTIFICATION_WARNING_BORDER: "#ffc107",
        
        # エラー通知（赤）
        ThemeKey.NOTIFICATION_ERROR_BACKGROUND: "#ffebee",
        ThemeKey.NOTIFICATION_ERROR_TEXT: "#c62828",
        ThemeKey.NOTIFICATION_ERROR_BORDER: "#f44336",
        
        # ========================================
        # ComboBox - コンボボックス
        # ========================================
        ThemeKey.COMBO_BACKGROUND: "#fafbfc",  # 極薄灰色（INPUT背景と差別化）
        ThemeKey.COMBO_BORDER: "#cccccc",
        ThemeKey.COMBO_BORDER_FOCUS: "#2196F3",
        ThemeKey.COMBO_BACKGROUND_FOCUS: "#e3f2fd",
        ThemeKey.COMBO_ARROW_BACKGROUND: "#2196F3",
        ThemeKey.COMBO_ARROW_BACKGROUND_PRESSED: "#1976D2",
        ThemeKey.COMBO_DROPDOWN_BACKGROUND: "#F5F5F5",
        ThemeKey.COMBO_DROPDOWN_BORDER: "#1565C0",
        
        # ========================================
        # ScrollBar - スクロールバー
        # ========================================
        ThemeKey.SCROLLBAR_BACKGROUND: "#f8f9fa",
        ThemeKey.SCROLLBAR_HANDLE: "#6c757d",
        ThemeKey.SCROLLBAR_HANDLE_HOVER: "#495057",
        
        # ========================================
        # Status - ステータス表示
        # ========================================
        ThemeKey.STATUS_BACKGROUND: "#f0f0f0",
        ThemeKey.STATUS_BORDER: "#ddd",
        ThemeKey.STATUS_TEXT: "#666666",
        ThemeKey.STATUS_SUCCESS: "#2e7d32",  # 成功状態（緑）
        ThemeKey.STATUS_WARNING: "#e65100",  # 警告状態（オレンジ）
        ThemeKey.STATUS_ERROR: "#dc3545",  # エラー状態（赤）
        
        # ========================================
        # GroupBox - グループボックス
        # ========================================
        # WINDOW_BACKGROUND(#ffffff)より僅かに暗くし層差を明確化
        ThemeKey.GROUPBOX_BACKGROUND: "#f5f5f5",
        ThemeKey.GROUPBOX_BORDER: "#2196f3",
        ThemeKey.GROUPBOX_TITLE_TEXT: "#2196f3",
        
        # ========================================
        # Overlay - オーバーレイ・モーダル
        # ========================================
        ThemeKey.OVERLAY_BACKGROUND: "rgba(168, 207, 118, 0.5)",
        ThemeKey.OVERLAY_TEXT: "rgba(0, 0, 0, 1)",
        
        # ========================================
        # Icon - アイコン
        # ========================================
        ThemeKey.ICON_PRIMARY: "#2196f3",
        ThemeKey.ICON_SECONDARY: "#757575",
        ThemeKey.ICON_SUCCESS: "#4caf50",
        ThemeKey.ICON_WARNING: "#ff9800",
        ThemeKey.ICON_DANGER: "#f44336",
        
        # ========================================
        # Markdown - マークダウン表示
        # ========================================
        ThemeKey.MARKDOWN_H1_TEXT: "#2c3e50",
        ThemeKey.MARKDOWN_H1_BORDER: "#3498db",
        ThemeKey.MARKDOWN_H2_TEXT: "#34495e",
        ThemeKey.MARKDOWN_H2_BORDER: "#bdc3c7",
        ThemeKey.MARKDOWN_H3_TEXT: "#7f8c8d",
        ThemeKey.MARKDOWN_CODE_BACKGROUND: "#f4f4f4",
        ThemeKey.MARKDOWN_BLOCKQUOTE_BORDER: "#3498db",
        ThemeKey.MARKDOWN_BLOCKQUOTE_TEXT: "#7f8c8d",
        ThemeKey.MARKDOWN_LINK: "#3498db",
        
        # ========================================
        # Portal - データポータル専用
        # ========================================
        ThemeKey.PORTAL_DATASET_ROW_BACKGROUND: "#e8f4f8",
        ThemeKey.PORTAL_DATASET_ROW_BACKGROUND_HOVER: "#d0e8f0",
        ThemeKey.PORTAL_THUMBNAIL_BORDER: "#ccc",
        ThemeKey.PORTAL_THUMBNAIL_BACKGROUND: "#f0f0f0",
        
        # ========================================
        # Data Entry - データ登録UI専用
        # ========================================
        # スクロールエリア
        ThemeKey.DATA_ENTRY_SCROLL_AREA_BACKGROUND: "#fefefe",  # 極薄灰（WINDOW背景と差別化）
        ThemeKey.DATA_ENTRY_SCROLL_AREA_BORDER: "#dee2e6",
        
        # データ登録タブコンテナ
        # タブコンテナ（選択中ペインの外側）: 白系に寄り過ぎないよう僅かに暗くする
        ThemeKey.DATA_ENTRY_TAB_CONTAINER_BACKGROUND: "#eef0f2",
        
        # ファイルツリー（一括登録）
        ThemeKey.FILE_TREE_BACKGROUND: "#fefefe",  # 極薄灰（WINDOW背景と差別化）
        ThemeKey.FILE_TREE_TEXT: "#212529",
        ThemeKey.FILE_TREE_BORDER: "#dee2e6",
        ThemeKey.FILE_TREE_HEADER_BACKGROUND: "#f8f9fa",
        ThemeKey.FILE_TREE_HEADER_TEXT: "#495057",
        ThemeKey.FILE_TREE_ROW_ALTERNATE: "#f8f9fa",
        ThemeKey.FILE_TREE_ROW_HOVER: "#e9ecef",
        ThemeKey.FILE_TREE_ROW_SELECTED: "#e3f2fd",
        
        # ファイルセットテーブル（一括登録）
        ThemeKey.FILESET_TABLE_BACKGROUND: "#fdfdfd",  # オフホワイト（TABLE背景と統一）
        ThemeKey.FILESET_TABLE_BORDER: "#dee2e6",
        ThemeKey.FILESET_TABLE_HEADER_BACKGROUND: "#f8f9fa",
        ThemeKey.FILESET_TABLE_HEADER_TEXT: "#495057",
        ThemeKey.FILESET_TABLE_ROW_ALTERNATE: "#f8f9fa",
        ThemeKey.FILESET_TABLE_ROW_HOVER: "#e9ecef",
        
        # プレビューダイアログ
        ThemeKey.PREVIEW_DIALOG_BACKGROUND: "#fefefe",  # 極薄灰（WINDOW背景と差別化）
        ThemeKey.PREVIEW_DIALOG_TEXT: "#212529",
        ThemeKey.PREVIEW_DIALOG_BORDER: "#dee2e6",
        
        # 情報表示ラベル
        ThemeKey.INFO_LABEL_BACKGROUND: "#e3f2fd",
        ThemeKey.INFO_LABEL_TEXT: "#1976d2",
        ThemeKey.INFO_LABEL_BORDER: "#1976d2",
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
