"""
研究資金番号入力ウィジェット
入力ボックス+追加ボタン+一覧表示のUIコンポーネント
"""
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox
)
from qt_compat.core import Signal, Qt
from classes.theme import get_color, get_qcolor, ThemeKey, ThemeManager


class FundingNumberWidget(QWidget):
    """研究資金番号入力専用ウィジェット"""
    
    # データ変更時のシグナル
    dataChanged = Signal()
    
    def __init__(self, initial_numbers=None):
        """
        Args:
            initial_numbers (list or str): 初期資金番号リスト ["番号1", "番号2", ...] またはカンマ区切り文字列
        """
        super().__init__()
        
        # 初期データの変換
        if isinstance(initial_numbers, str):
            self.funding_numbers = [n.strip() for n in initial_numbers.split(',') if n.strip()]
        elif isinstance(initial_numbers, list):
            self.funding_numbers = [str(n).strip() for n in initial_numbers if str(n).strip()]
        else:
            self.funding_numbers = []
        
        self.setup_ui()
        self.populate_table()
    
    def setup_ui(self):
        """UIセットアップ"""
        # 領域背景（研究資金領域）
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.panel = QWidget()
        self.panel.setObjectName("subgroup_funding_panel")
        self.panel.setStyleSheet(
            f"background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)}; "
            f"border: 1px solid {get_color(ThemeKey.PANEL_BORDER)}; border-radius: 4px;"
        )
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        
        # 入力フォーム部分
        form_layout = QHBoxLayout()
        
        self.number_input = QLineEdit()
        self.number_input.setPlaceholderText("例: FUND0001")
        self.number_input.setMinimumWidth(200)
        form_layout.addWidget(self.number_input)
        
        # 追加ボタン
        self.add_button = QPushButton("追加")
        self.add_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
        """)
        self.add_button.clicked.connect(self.add_funding_number)
        form_layout.addWidget(self.add_button)
        
        # 全削除ボタン
        self.clear_button = QPushButton("全削除")
        self.clear_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
                padding: 5px 15px;
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
            }}
        """)
        self.clear_button.clicked.connect(self.clear_all)
        form_layout.addWidget(self.clear_button)
        
        form_layout.addStretch()
        # フォームはテーブルの下に配置（レイアウト順維持）
        # 先にテーブルを追加し、その下にフォームを置く
        
        # テーブル部分
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(2)  # 研究資金番号, 削除
        self.table_widget.setHorizontalHeaderLabels(["研究資金番号", "削除"])
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setMaximumHeight(120)
        self.table_widget.setMinimumHeight(80)
        
        # 列幅設定
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)    # 研究資金番号列
        header.setSectionResizeMode(1, QHeaderView.Fixed)      # 削除列
        self.table_widget.setColumnWidth(1, 60)   # 削除列
        
        # テーブルスタイル
        from qt_compat.gui import QPalette
        palette = self.table_widget.palette()
        palette.setColor(QPalette.Base, get_qcolor(ThemeKey.TABLE_BACKGROUND))
        palette.setColor(QPalette.AlternateBase, get_qcolor(ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE))
        palette.setColor(QPalette.Text, get_qcolor(ThemeKey.TABLE_ROW_TEXT))
        self.table_widget.setPalette(palette)
        
        self.table_widget.setStyleSheet(f"""
            QTableWidget {{
                gridline-color: {get_color(ThemeKey.TABLE_BORDER)};
                border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            QHeaderView::section {{
                background-color: {get_color(ThemeKey.TABLE_HEADER_BACKGROUND)};
                color: {get_color(ThemeKey.TABLE_HEADER_TEXT)};
                font-weight: bold;
                padding: 5px;
                border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
            }}
        """)
        
        layout.addWidget(self.table_widget)
        layout.addLayout(form_layout)

        outer_layout.addWidget(self.panel)
        
        # Enterキーで追加
        self.number_input.returnPressed.connect(self.add_funding_number)
        
        self.setLayout(outer_layout)
        
        # ThemeManager接続
        theme_manager = ThemeManager.instance()
        theme_manager.theme_changed.connect(self.refresh_theme)
    
    def populate_table(self):
        """テーブルを初期データで埋める"""
        self.table_widget.setRowCount(len(self.funding_numbers))
        
        for row, number in enumerate(self.funding_numbers):
            # 研究資金番号列
            number_item = QTableWidgetItem(number)
            number_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table_widget.setItem(row, 0, number_item)
            
            # 削除ボタン
            delete_button = QPushButton("×")
            delete_button.setStyleSheet(
                f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                        border: none;
                        padding: 2px 8px;
                        border-radius: 2px;
                        font-size: 12px;
                        max-width: 40px;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
                    }}
                    QPushButton:pressed {{
                        background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED)};
                    }}
                """
            )
            delete_button.clicked.connect(lambda checked, r=row: self.delete_row(r))
            self.table_widget.setCellWidget(row, 1, delete_button)
    
    def add_funding_number(self):
        """資金番号を追加"""
        number = self.number_input.text().strip()
        if not number:
            QMessageBox.warning(self, "入力エラー", "研究資金番号を入力してください。")
            self.number_input.setFocus()
            return
        
        # 重複チェック
        if number in self.funding_numbers:
            QMessageBox.information(self, "重複エラー", f"研究資金番号 '{number}' は既に追加されています。")
            self.number_input.setFocus()
            return
        
        # リストに追加
        self.funding_numbers.append(number)
        self.populate_table()
        self.number_input.clear()
        self.number_input.setFocus()
        
        # 変更通知
        self.dataChanged.emit()
    
    def delete_row(self, row):
        """指定行を削除"""
        if 0 <= row < len(self.funding_numbers):
            # リストから削除
            self.funding_numbers.pop(row)
            self.populate_table()
            
            # 変更通知
            self.dataChanged.emit()
    
    def clear_all(self):
        """全削除"""
        if not self.funding_numbers:
            return
        
        reply = QMessageBox.question(
            self, 
            "確認", 
            "全ての研究資金番号を削除しますか？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.funding_numbers.clear()
            self.populate_table()
            self.dataChanged.emit()
    
    def get_funding_numbers(self):
        """現在の資金番号リストを取得"""
        return list(self.funding_numbers)
    
    def get_funding_numbers_as_string(self):
        """カンマ区切り文字列として取得（後方互換性）"""
        return ", ".join(self.funding_numbers)
    
    def set_funding_numbers(self, numbers):
        """資金番号リストを設定"""
        if isinstance(numbers, str):
            self.funding_numbers = [n.strip() for n in numbers.split(',') if n.strip()]
        elif isinstance(numbers, list):
            self.funding_numbers = [str(n).strip() for n in numbers if str(n).strip()]
        else:
            self.funding_numbers = []
        
        self.populate_table()
        self.dataChanged.emit()
    
    def refresh_theme(self):
        """テーマ切替時の更新処理"""
        try:
            if hasattr(self, "panel") and self.panel:
                self.panel.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)}; "
                    f"border: 1px solid {get_color(ThemeKey.PANEL_BORDER)}; border-radius: 4px;"
                )

            # ボタンスタイル再適用
            self.add_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                    border: none;
                    padding: 5px 15px;
                    border-radius: 3px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
                }}
            """)
            
            self.clear_button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                    border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
                    padding: 5px 15px;
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
                }}
            """)
            
            # テーブルスタイル再適用
            from qt_compat.gui import QPalette
            palette = self.table_widget.palette()
            palette.setColor(QPalette.Base, get_qcolor(ThemeKey.TABLE_BACKGROUND))
            palette.setColor(QPalette.AlternateBase, get_qcolor(ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE))
            palette.setColor(QPalette.Text, get_qcolor(ThemeKey.TABLE_ROW_TEXT))
            self.table_widget.setPalette(palette)
            
            self.table_widget.setStyleSheet(f"""
                QTableWidget {{
                    gridline-color: {get_color(ThemeKey.TABLE_BORDER)};
                    border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
                }}
                QTableWidget::item {{
                    padding: 4px;
                }}
                QHeaderView::section {{
                    background-color: {get_color(ThemeKey.TABLE_HEADER_BACKGROUND)};
                    color: {get_color(ThemeKey.TABLE_HEADER_TEXT)};
                    font-weight: bold;
                    padding: 5px;
                    border: 1px solid {get_color(ThemeKey.TABLE_BORDER)};
                }}
            """)

            # 削除ボタン（×）のスタイルを再適用
            for row in range(self.table_widget.rowCount()):
                w = self.table_widget.cellWidget(row, 1)
                if isinstance(w, QPushButton) and w.text() == "×":
                    w.setStyleSheet(
                        f"""
                            QPushButton {{
                                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                                border: none;
                                padding: 2px 8px;
                                border-radius: 2px;
                                font-size: 12px;
                                max-width: 40px;
                            }}
                            QPushButton:hover {{
                                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
                            }}
                            QPushButton:pressed {{
                                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_PRESSED)};
                            }}
                        """
                    )
            
            self.update()
        except Exception as e:
            pass


def create_funding_number_widget(initial_numbers=None):
    """研究資金番号ウィジェット作成ファクトリ関数"""
    return FundingNumberWidget(initial_numbers)
