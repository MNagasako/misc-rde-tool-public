"""
選択的置換ダイアログ（装置・プロセス、論文・プロシーディング用）

既存項目と新規候補を比較表示し、選択的に置換・追加・削除を行うダイアログ。
10行まではスクロール不要、それ以上は固定高さでスクロール表示。

アクションモード:
- 全置換: 新規候補ですべて置き換える
- 通常置換: 既存+新規でセット演算(union)して重複自動削除
- 選択置換: チェックされた項目のみを反映
"""
from typing import List, Dict, Any, Optional, Callable
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QRadioButton, QButtonGroup, QGroupBox, QMessageBox, QScrollArea,
    QWidget
)
from qt_compat.core import Qt
from qt_compat.gui import QBrush

from classes.theme import get_color, get_qcolor, ThemeKey
from classes.managers.log_manager import get_logger

logger = get_logger("DataPortal.SelectiveReplacementDialog")


class SelectiveReplacementDialog(QDialog):
    """装置・論文用の選択的置換ダイアログ"""

    def __init__(self,
                 title: str,
                 field_prefix: str,
                 current_items: List[str],
                 suggested_items: List[str],
                 normalizer: Optional[Callable[[str], str]] = None,
                 extension_buttons: Optional[List[Dict[str, Any]]] = None,
                 parent=None):
        """
        Args:
            title: ダイアログタイトル（例: "装置・プロセス 選択的置換"）
            field_prefix: フィールド接頭辞（例: "t_equip_process"）
            current_items: 既存のテーブル内容（空文字列含む全行）
            suggested_items: 報告書から取得した候補
            normalizer: 重複判定用の正規化関数（デフォルト: 文字列正規化）
            extension_buttons: 拡張機能ボタン定義リスト [{"label": str, "callback": Callable[[int, str], str]}, ...]
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(900)
        self.setMinimumHeight(600)

        self.field_prefix = field_prefix
        self.current_items = current_items
        self.suggested_items = suggested_items
        self.normalizer = normalizer or self._default_normalizer
        # 論文・プロシーディングの場合は機能列を表示しない
        self.extension_buttons = extension_buttons if field_prefix == 't_equip_process' else []

        # 結果格納
        self.final_items: List[str] = []
        self._accepted = False

        # 比較データ構造
        self.comparison_data: List[Dict[str, Any]] = []

        self._init_ui()
        self._build_comparison_table()

    def _default_normalizer(self, text: str) -> str:
        """デフォルトの正規化処理（空白除去・小文字化）"""
        return text.strip().lower()

    def _init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)

        # アクション選択
        action_group = self._create_action_group()
        layout.addWidget(action_group)

        # 重複削除オプション
        self.remove_duplicates_checkbox = QCheckBox("重複を自動削除")
        self.remove_duplicates_checkbox.setChecked(True)
        layout.addWidget(self.remove_duplicates_checkbox)

        # 比較テーブル
        table_label = QLabel("既存項目と新規候補の比較:")
        layout.addWidget(table_label)

        self.table = QTableWidget()
        # 機能列は装置・プロセスのみ表示
        col_count = 4 if self.extension_buttons else 3
        self.table.setColumnCount(col_count)
        
        if self.extension_buttons:
            self.table.setHorizontalHeaderLabels(["選択", "既存項目", "新規候補", "機能"])
        else:
            self.table.setHorizontalHeaderLabels(["選択", "既存項目", "新規候補"])
        
        # ヘッダー設定
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 選択列
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # 既存項目
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # 新規候補
        if self.extension_buttons:
            header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # 機能列

        # 20行固定表示、10行分のスクロール可能領域
        row_height = 30
        max_visible_rows = 10
        header_height = self.table.horizontalHeader().height()
        max_table_height = header_height + (row_height * max_visible_rows)
        self.table.setMaximumHeight(max_table_height)

        layout.addWidget(self.table)

        # 適用/キャンセルボタン
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("キャンセル")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("適用")
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _create_action_group(self) -> QGroupBox:
        """アクション選択ラジオボタングループを作成"""
        group = QGroupBox("アクション選択")
        layout = QHBoxLayout()

        self.action_btn_group = QButtonGroup(self)
        
        self.replace_all_radio = QRadioButton("全置換")
        self.replace_all_radio.setToolTip("新規候補ですべて置き換える")
        self.action_btn_group.addButton(self.replace_all_radio, 0)
        layout.addWidget(self.replace_all_radio)

        self.normal_replace_radio = QRadioButton("通常置換")
        self.normal_replace_radio.setToolTip("既存+新規でセット演算(union)して重複自動削除")
        self.normal_replace_radio.setChecked(True)  # デフォルト
        self.action_btn_group.addButton(self.normal_replace_radio, 1)
        layout.addWidget(self.normal_replace_radio)

        self.selective_replace_radio = QRadioButton("選択置換")
        self.selective_replace_radio.setToolTip("チェックされた項目のみを反映")
        self.action_btn_group.addButton(self.selective_replace_radio, 2)
        layout.addWidget(self.selective_replace_radio)

        layout.addStretch()
        group.setLayout(layout)
        return group

    def _build_comparison_table(self):
        """既存項目と新規候補を比較してテーブル構築"""
        # 正規化マップ作成
        current_map = {}  # normalized -> original
        for item in self.current_items:
            if item:  # 空文字列は除外
                norm = self.normalizer(item)
                if norm and norm not in current_map:  # 最初の出現を保持
                    current_map[norm] = item

        suggested_map = {}
        for item in self.suggested_items:
            if item:
                norm = self.normalizer(item)
                if norm and norm not in suggested_map:
                    suggested_map[norm] = item

        # 差分・重複検出
        current_keys = set(current_map.keys())
        suggested_keys = set(suggested_map.keys())

        duplicates = current_keys & suggested_keys
        only_current = current_keys - duplicates
        only_suggested = suggested_keys - duplicates

        # 比較データ構築
        self.comparison_data = []

        # 重複項目
        for norm in sorted(duplicates):
            self.comparison_data.append({
                'type': 'duplicate',
                'normalized': norm,
                'current': current_map[norm],
                'suggested': suggested_map[norm],
                'checked': False  # デフォルトはチェックなし（既存を維持）
            })

        # 既存のみ
        for norm in sorted(only_current):
            self.comparison_data.append({
                'type': 'current_only',
                'normalized': norm,
                'current': current_map[norm],
                'suggested': '',
                'checked': True  # デフォルトで保持
            })

        # 新規のみ
        for norm in sorted(only_suggested):
            self.comparison_data.append({
                'type': 'suggested_only',
                'normalized': norm,
                'current': '',
                'suggested': suggested_map[norm],
                'checked': True  # デフォルトで追加
            })

        # テーブル構築（常に20行表示）
        self.table.setRowCount(20)

        for row, data in enumerate(self.comparison_data):
            # 選択チェックボックス
            checkbox = QCheckBox()
            checkbox.setChecked(data['checked'])
            checkbox_widget = self._create_centered_widget(checkbox)
            self.table.setCellWidget(row, 0, checkbox_widget)

            # 既存項目
            current_item = QTableWidgetItem(data['current'])
            current_item.setFlags(Qt.ItemIsEnabled)  # 編集不可
            if data['type'] == 'current_only':
                current_item.setBackground(QBrush(get_qcolor(ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE)))
            self.table.setItem(row, 1, current_item)

            # 新規候補
            suggested_item = QTableWidgetItem(data['suggested'])
            suggested_item.setFlags(Qt.ItemIsEnabled)
            if data['type'] == 'suggested_only':
                suggested_item.setBackground(QBrush(get_qcolor(ThemeKey.PANEL_INFO_BACKGROUND)))
            elif data['type'] == 'duplicate':
                suggested_item.setBackground(QBrush(get_qcolor(ThemeKey.PANEL_WARNING_BACKGROUND)))
            self.table.setItem(row, 2, suggested_item)

            # 拡張機能ボタン（装置・プロセスのみ）
            if self.extension_buttons:
                btn_widget = self._create_extension_buttons(row)
                self.table.setCellWidget(row, 3, btn_widget)
        
        # 残りの空行を初期化（20行に満たない場合）
        for row in range(len(self.comparison_data), 20):
            # 空のチェックボックス
            checkbox = QCheckBox()
            checkbox.setChecked(False)
            checkbox_widget = self._create_centered_widget(checkbox)
            self.table.setCellWidget(row, 0, checkbox_widget)
            
            # 空のテキストアイテム
            self.table.setItem(row, 1, QTableWidgetItem(""))
            self.table.setItem(row, 2, QTableWidgetItem(""))
            if self.extension_buttons:
                self.table.setItem(row, 3, QTableWidgetItem(""))
            
            # comparison_dataにも空エントリ追加
            self.comparison_data.append({
                'type': 'empty',
                'normalized': '',
                'current': '',
                'suggested': '',
                'checked': False
            })

    def _create_centered_widget(self, widget) -> QWidget:
        """ウィジェットを中央配置したコンテナを作成"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.addWidget(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        return container

    def _create_extension_buttons(self, row: int) -> QWidget:
        """拡張機能ボタンを作成"""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        for btn_def in self.extension_buttons:
            btn = QPushButton(btn_def.get("label", "機能"))
            btn.setMaximumWidth(80)
            btn.clicked.connect(lambda checked=False, r=row, callback=btn_def.get("callback"): 
                               self._on_extension_button_clicked(r, callback))
            layout.addWidget(btn)

        layout.addStretch()
        return container

    def _on_extension_button_clicked(self, row: int, callback: Optional[Callable[[int, str, str], str]]):
        """拡張機能ボタンクリック時の処理"""
        if not callback:
            return

        try:
            data = self.comparison_data[row]
            current_text = data['current']
            suggested_text = data['suggested']

            # コールバック実行（行番号、既存テキスト、新規テキストを渡す）
            result = callback(row, current_text, suggested_text)

            if result is not None:
                # 結果を適用（新規候補に反映）
                data['suggested'] = result
                self.table.item(row, 2).setText(result)
                logger.debug(f"拡張機能適用: row={row}, result={result}")

        except Exception as e:
            logger.error(f"拡張機能実行エラー: {e}", exc_info=True)
            QMessageBox.warning(self, "エラー", f"拡張機能実行中にエラーが発生しました:\n{e}")

    def _on_apply(self):
        """適用ボタン押下時の処理"""
        try:
            action_id = self.action_btn_group.checkedId()
            remove_duplicates = self.remove_duplicates_checkbox.isChecked()

            if action_id == 0:  # 全置換
                self.final_items = self._build_merged_items_replace_all()
            elif action_id == 1:  # 通常置換
                self.final_items = self._build_merged_items_normal(remove_duplicates)
            elif action_id == 2:  # 選択置換
                self.final_items = self._build_merged_items_selective(remove_duplicates)
            else:
                QMessageBox.warning(self, "エラー", "アクションが選択されていません。")
                return

            logger.info(f"適用完了: action_id={action_id}, final_count={len(self.final_items)}")
            self._accepted = True
            self.accept()

        except Exception as e:
            logger.error(f"適用処理エラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"適用処理中にエラーが発生しました:\n{e}")

    def _build_merged_items_replace_all(self) -> List[str]:
        """全置換: 新規候補ですべて置き換える"""
        return [item for item in self.suggested_items if item]

    def _build_merged_items_normal(self, remove_duplicates: bool) -> List[str]:
        """通常置換: 既存+新規でセット演算(union)"""
        current_set = set(item for item in self.current_items if item)
        suggested_set = set(item for item in self.suggested_items if item)

        if remove_duplicates:
            # 正規化キーでセット演算
            merged = {}  # normalized -> original
            for item in current_set:
                norm = self.normalizer(item)
                if norm and norm not in merged:
                    merged[norm] = item
            for item in suggested_set:
                norm = self.normalizer(item)
                if norm and norm not in merged:
                    merged[norm] = item
            return list(merged.values())
        else:
            # 単純なunion
            return list(current_set.union(suggested_set))

    def _build_merged_items_selective(self, remove_duplicates: bool) -> List[str]:
        """選択置換: チェックされた項目のみを反映"""
        selected_items = []

        for row, data in enumerate(self.comparison_data):
            # 空行（type='empty'）はスキップ
            if data.get('type') == 'empty':
                continue
                
            checkbox_widget = self.table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    # 新規候補が存在すればそれを、なければ既存を採用
                    item = data['suggested'] if data['suggested'] else data['current']
                    if item:
                        selected_items.append(item)

        if remove_duplicates:
            # 正規化キーで重複削除
            merged = {}
            for item in selected_items:
                norm = self.normalizer(item)
                if norm and norm not in merged:
                    merged[norm] = item
            return list(merged.values())
        else:
            return selected_items



    def get_result(self) -> Dict[str, Any]:
        """
        適用結果を取得

        Returns:
            {
                'accepted': bool,
                'action': str ('replace_all' / 'normal' / 'selective'),
                'final_items': List[str],
                'item_count': int
            }
        """
        action_id = self.action_btn_group.checkedId()
        action_names = {0: 'replace_all', 1: 'normal', 2: 'selective'}
        action = action_names.get(action_id, 'unknown')

        return {
            'accepted': self._accepted,
            'action': action,
            'final_items': self.final_items,
            'item_count': len(self.final_items)
        }
