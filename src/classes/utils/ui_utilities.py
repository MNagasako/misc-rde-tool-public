"""
UI関連のユーティリティクラス - ARIM RDE Tool v1.13.1
UIControllerから分離したユーティリティメソッド群
"""
from qt_compat.widgets import QPushButton
from qt_compat.gui import QFontMetrics, QFont
from classes.utils.ui_dialogs import TextAreaExpandDialog


class UIUtilities:
    """UI関連のユーティリティメソッドを集めたクラス"""
    
    @staticmethod
    def create_expand_button(parent_controller, text_widget, title):
        """テキストエリア用の拡大表示ボタンを作成"""
        expand_btn = QPushButton("🔍")
        expand_btn.setToolTip("拡大表示")
        expand_btn.setStyleSheet("""
            QPushButton {
                background-color: #e3f2fd;
                border: 1px solid #2196f3;
                border-radius: 12px;
                width: 24px;
                height: 24px;
                font-size: 12px;
                color: #1976d2;
            }
            QPushButton:hover {
                background-color: #bbdefb;
            }
            QPushButton:pressed {
                background-color: #90caf9;
            }
        """)
        expand_btn.setMaximumSize(24, 24)
        expand_btn.setMinimumSize(24, 24)
        
        # クリック時の処理を設定
        def show_expanded():
            parent_controller.show_text_area_expanded(text_widget, title)
        
        expand_btn.clicked.connect(show_expanded)
        return expand_btn
    
    @staticmethod
    def create_auto_resize_button(text, width, height, base_style):
        """フォントサイズ自動調整機能付きボタンを作成"""
        button = QPushButton(text)
        button.setMinimumSize(width, height)
        button.setMaximumSize(width * 2, height * 2)  # 最大サイズ制限
        
        # フォントサイズを自動調整
        adjusted_font_size = UIUtilities._calculate_font_size(text, width, height)
        
        # ベーススタイルにフォントサイズを追加
        style_with_font = f"{base_style} font-size: {adjusted_font_size}px;"
        button.setStyleSheet(style_with_font)
        
        return button
    
    @staticmethod
    def _calculate_font_size(text, target_width, target_height):
        """テキストがボタンサイズに収まるフォントサイズを計算"""
        font = QFont()
        
        # 初期フォントサイズから開始
        font_size = 14
        font.setPointSize(font_size)
        metrics = QFontMetrics(font)
        
        # テキスト幅がターゲット幅の80%以内に収まるまでフォントサイズを調整
        target_text_width = target_width * 0.8
        target_text_height = target_height * 0.6
        
        while font_size > 8:  # 最小フォントサイズ
            font.setPointSize(font_size)
            metrics = QFontMetrics(font)
            text_width = metrics.horizontalAdvance(text)
            text_height = metrics.height()
            
            if text_width <= target_text_width and text_height <= target_text_height:
                break
            
            font_size -= 1
        
        return max(font_size, 8)  # 最小8pxを保証
    
    @staticmethod
    def create_info_expand_button(title, tooltip_text):
        """情報表示用の拡大表示ボタンを作成（専用）"""
        expand_btn = QPushButton("🔍")
        expand_btn.setToolTip(tooltip_text)
        expand_btn.setStyleSheet("""
            QPushButton {
                background-color: #e3f2fd;
                border: 1px solid #2196f3;
                border-radius: 12px;
                width: 24px;
                height: 24px;
                font-size: 12px;
                color: #1976d2;
            }
            QPushButton:hover {
                background-color: #bbdefb;
            }
            QPushButton:pressed {
                background-color: #90caf9;
            }
        """)
        expand_btn.setMaximumSize(24, 24)
        expand_btn.setMinimumSize(24, 24)
        
        return expand_btn
