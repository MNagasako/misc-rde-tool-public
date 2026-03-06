"""
データポータル修正ダイアログ

データポータルに登録済みのエントリを修正するためのダイアログ
"""

import json
import logging
import re
import html as html_lib
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QTextEdit, QPushButton,
    QGroupBox, QMessageBox, QProgressDialog, QApplication, QScrollArea, QWidget, QCheckBox, QRadioButton, QButtonGroup, QListWidget, QAbstractItemView,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialogButtonBox, QDateTimeEdit, QGridLayout
)
from qt_compat.core import QDateTime, Qt
from qt_compat import get_screen_geometry

from classes.theme import get_color, ThemeKey

from classes.managers.log_manager import get_logger
from classes.data_portal.ui.widgets import FilterableCheckboxTable
from classes.dataset.util.data_entry_summary import (
    get_data_entry_summary,
    format_size_with_bytes,
)
from classes.dataset.core.dataset_dataentry_logic import fetch_dataset_dataentry
from core.bearer_token_manager import BearerTokenManager

from classes.data_portal.util.public_output_paths import (
    find_latest_matching_file,
    get_public_data_portal_root_dir,
)
from classes.data_portal.util.related_catalog_builder import (
    build_related_catalog_html,
    extract_related_dataset_ids,
    find_related_catalog_candidates,
    normalize_public_portal_records,
)
from config.common import get_dynamic_file_path

logger = get_logger("DataPortal.PortalEditDialog")


def extract_equipment_code_only(text: str) -> str:
    """装置候補の表示テキストから、装置コード(例: NM-005)のみを抽出して返す。

    - 表示は「NM-005:装置名」などを許容
    - アンカータグ等の混在も許容
    - 抽出できない場合は、元テキストのstripを返す
    """
    try:
        from classes.utils.facility_link_helper import extract_equipment_id

        equip_id = extract_equipment_id(text or "")
        return equip_id if equip_id else (text or "").strip()
    except Exception:
        return (text or "").strip()


class PortalEditDialog(QDialog):
    """データカタログ修正ダイアログ"""

    _ZERO_DEFAULT_FIELDS = {
        't_file_count',
        't_meta_totalfilesize',
        't_meta_totalfilesizeinthisversion',
    }
    
    def __init__(
        self,
        form_data: Dict[str, Any],
        t_code: str,
        dataset_id: str,
        portal_client,
        parent=None,
        metadata: Optional[Dict[str, Any]] = None,
        environment: str = "production",
    ):
        """
        初期化
        
        Args:
            form_data: フォームデータ（_parse_edit_formの戻り値）
            t_code: テーマコード
            dataset_id: データセットID
            portal_client: PortalClientインスタンス
            parent: 親ウィジェット
            metadata: メタデータ（選択肢情報）
        """
        super().__init__(parent)
        
        self.form_data = form_data
        self.t_code = t_code
        self.dataset_id = dataset_id
        self.portal_client = portal_client
        self.metadata = metadata or {}
        self.environment = str(environment or "production").strip() or "production"
        self.field_widgets = {}
        self.file_stats_auto_button = None
        
        self.setWindowTitle(f"データカタログ修正 [{self._get_environment_display_name()}] - {dataset_id[:8]}...")
        self.setMinimumWidth(800)
        
        # 初期ウィンドウ高さを画面高さ - 100px に設定
        screen_rect = get_screen_geometry(self)
        initial_height = max(600, screen_rect.height() - 100)  # 最低600pxを保証
        self.resize(800, initial_height)
        
        self._init_ui()
        logger.info(f"修正ダイアログ初期化: t_code={t_code}, dataset_id={dataset_id}, metadata={len(self.metadata)}項目")

    def _get_environment_display_name(self) -> str:
        return "テスト環境" if self.environment == "test" else "本番環境"

    def _get_environment_site_url(self) -> str:
        try:
            from classes.data_portal.conf.config import get_data_portal_config

            return str(get_data_portal_config().get_url(self.environment) or "").strip()
        except Exception:
            return ""

    def _build_environment_message(self) -> str:
        lines = [f"操作対象: {self._get_environment_display_name()}"]
        site_url = self._get_environment_site_url()
        if site_url:
            lines.append(f"対象サイト: {site_url}")
        return "\n".join(lines)
    
    def _init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        
        # スクロールエリア
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # 設定ダイアログ用の編集ウィジェット退避領域（常に非表示）
        self._hidden_editors = QWidget()
        self._hidden_editors_layout = QVBoxLayout(self._hidden_editors)
        self._hidden_editors_layout.setContentsMargins(0, 0, 0, 0)
        self._hidden_editors_layout.setSpacing(0)
        self._hidden_editors.setVisible(False)
        self._summary_labels: dict[str, QLabel] = {}
        
        # 主要項目グループ
        main_group = self._create_main_fields_group()
        scroll_layout.addWidget(main_group)
        
        # その他の項目グループ
        other_group = self._create_other_fields_group()
        scroll_layout.addWidget(other_group)

        # 退避領域を末尾に追加（非表示のまま保持）
        scroll_layout.addWidget(self._hidden_editors)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("キャンセル")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
        """)
        button_layout.addWidget(self.save_btn)
        
        layout.addLayout(button_layout)
    
    def _create_main_fields_group(self) -> QGroupBox:
        """主要項目グループを作成"""
        group = QGroupBox("主要項目")
        layout = QFormLayout()
        
        # 機関 (t_mi_code)
        if 't_mi_code' in self.form_data and self.form_data['t_mi_code']['type'] == 'select':
            field_data = self.form_data['t_mi_code']
            combo = QComboBox()
            combo.setMaximumWidth(600)  # 最大幅を設定
            for opt in field_data['options']:
                combo.addItem(opt['text'], opt['value'])
                if opt['selected']:
                    combo.setCurrentText(opt['text'])
            self.field_widgets['t_mi_code'] = combo
            layout.addRow("機関:", combo)
        
        # ライセンスレベル (t_license_level)
        if 't_license_level' in self.form_data and self.form_data['t_license_level']['type'] == 'select':
            field_data = self.form_data['t_license_level']
            combo = QComboBox()
            combo.setMaximumWidth(600)  # 最大幅を設定
            for opt in field_data['options']:
                combo.addItem(opt['text'], opt['value'])
                if opt['selected']:
                    combo.setCurrentText(opt['text'])
            self.field_widgets['t_license_level'] = combo
            layout.addRow("ライセンスレベル:", combo)
        
        # 重要技術領域（主） (t_a_code)
        if 't_a_code' in self.form_data and self.form_data['t_a_code']['type'] == 'select':
            field_data = self.form_data['t_a_code']
            combo = QComboBox()
            for opt in field_data['options']:
                combo.addItem(opt['text'], opt['value'])
                if opt['selected']:
                    combo.setCurrentText(opt['text'])
            self.field_widgets['t_a_code'] = combo
            layout.addRow("重要技術領域（主）:", combo)
        
        # 重要技術領域（副） - 複数ある場合があるため動的に追加
        for key in self.form_data.keys():
            if key.startswith('t_a_sub_code'):
                field_data = self.form_data[key]
                if field_data['type'] == 'select':
                    combo = QComboBox()
                    for opt in field_data['options']:
                        combo.addItem(opt['text'], opt['value'])
                        if opt['selected']:
                            combo.setCurrentText(opt['text'])
                    self.field_widgets[key] = combo
                    label = field_data.get('label', key)
                    layout.addRow(f"{label}:", combo)
        
        self._apply_form_layout_row_styling(layout)
        group.setLayout(layout)
        return group

    def _apply_form_layout_row_styling(self, form_layout: QFormLayout) -> None:
        """QFormLayoutの各行を、ラベル強調 + 交互背景で視認性改善する（ThemeKey管理）"""
        try:
            rows = []
            while form_layout.rowCount() > 0:
                rows.append(form_layout.takeRow(0))

            for row_idx, row in enumerate(rows):
                label_item = row.labelItem
                field_item = row.fieldItem

                label_widget = label_item.widget() if label_item is not None else None
                field_widget = field_item.widget() if field_item is not None else None

                bg_key = ThemeKey.TABLE_ROW_BACKGROUND_ALTERNATE if (row_idx % 2 == 1) else ThemeKey.TABLE_ROW_BACKGROUND
                bg = get_color(bg_key)

                # label wrapper
                label_container = QWidget()
                label_container.setStyleSheet(f"background-color: {bg};")
                label_layout = QHBoxLayout(label_container)
                label_layout.setContentsMargins(8, 4, 8, 4)
                label_layout.setSpacing(0)

                if isinstance(label_widget, QLabel):
                    label_widget.setStyleSheet(
                        f"color: {get_color(ThemeKey.TEXT_SECONDARY)}; font-weight: bold;"
                    )
                    label_widget.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

                if label_widget is not None:
                    label_layout.addWidget(label_widget)

                # field wrapper
                field_container = QWidget()
                field_container.setStyleSheet(f"background-color: {bg};")
                field_layout = QHBoxLayout(field_container)
                field_layout.setContentsMargins(8, 4, 8, 4)
                field_layout.setSpacing(0)

                if field_widget is not None:
                    field_layout.addWidget(field_widget)

                form_layout.addRow(label_container, field_container)
        except Exception:
            # スタイル適用は補助機能のため失敗しても致命ではない
            return

    def _set_compact_autoset_button_width(self, btn: QPushButton) -> None:
        """自動設定ボタンの横幅を必要最小限に固定して、他行と揃える"""
        try:
            w = max(72, btn.sizeHint().width())
            btn.setFixedWidth(w)
        except Exception:
            return
    
    def _create_editable_list_table(
        self,
        field_prefix: str,
        label: str,
        max_rows: int = 20,
        visible_rows: int = 5,
        function_column_label: Optional[str] = None,
        function_widget_factory: Optional[Callable[[QTableWidget, int], QWidget]] = None,
    ):
        """
        編集可能なリストテーブルを作成（装置・プロセス、論文・プロシーディング用）
        常に20行表示、5行以上はスクロールバーで表示
        
        Args:
            field_prefix: フィールドのプレフィックス（例: 't_equip_process', 't_paper_proceed'）
            label: ラベル
            max_rows: 固定行数（常に20）
            visible_rows: スクロールなしで表示する行数（デフォルト5）
        
        Returns:
            QTableWidget: テーブルウィジェット
        """
        table = QTableWidget()
        table.verticalHeader().setSectionsMovable(True)  # 行番号ドラッグで並べ替え
        table.verticalHeader().setSectionsClickable(True)

        has_mapping_column = field_prefix == 't_equip_process'
        has_function_column = bool(function_column_label) and function_widget_factory is not None
        if has_function_column:
            if has_mapping_column:
                table.setColumnCount(3)
                table.setHorizontalHeaderLabels([label, '装置名', function_column_label])
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            else:
                table.setColumnCount(2)
                table.setHorizontalHeaderLabels([label, function_column_label])
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        else:
            if has_mapping_column:
                table.setColumnCount(2)
                table.setHorizontalHeaderLabels([label, '装置名'])
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            else:
                table.setColumnCount(1)
                table.setHorizontalHeaderLabels([label])
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        # 常に20行表示
        table.setRowCount(max_rows)
        
        # 既存データを読み込み
        function_col_widths: list[int] = []

        for i in range(1, max_rows + 1):
            field_name = f"{field_prefix}{i}"
            value = ""
            if field_name in self.form_data:
                value = self.form_data[field_name].get('value', '')
            
            item = QTableWidgetItem(value)
            table.setItem(i - 1, 0, item)

            if has_mapping_column:
                display_name = ""
                try:
                    fn = getattr(self, '_get_equipment_display_name', None)
                    if callable(fn):
                        display_name = fn(value)
                except Exception:
                    display_name = ""
                mapping_item = QTableWidgetItem(display_name)
                mapping_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                table.setItem(i - 1, 1, mapping_item)

            if has_function_column:
                widget = function_widget_factory(table, i - 1)
                func_col = 2 if has_mapping_column else 1
                table.setCellWidget(i - 1, func_col, widget)
                function_col_widths.append(widget.sizeHint().width())
        
        # 行の高さを設定
        table.verticalHeader().setDefaultSectionSize(25)

        if has_function_column and function_col_widths:
            # ボタン合計幅 + セル余白ぶん
            func_col = 2 if has_mapping_column else 1
            table.setColumnWidth(func_col, max(function_col_widths) + 18)
        
        # 5行分の表示高さに固定（それ以上はスクロール）
        table_height = visible_rows * 25 + table.horizontalHeader().height() + 2
        table.setMaximumHeight(table_height)
        table.setMinimumHeight(table_height)
        
        # 装置・プロセスは入力変更で名称列を更新
        if has_mapping_column:
            def _safe_on_changed(it, t=table, owner=self):
                try:
                    fn = getattr(owner, '_on_equip_process_item_changed', None)
                    if callable(fn):
                        fn(t, it)
                except Exception:
                    return

            table.itemChanged.connect(_safe_on_changed)

        return table

    def _get_equipment_display_name(self, raw_text: str) -> str:
        text = (raw_text or '').strip()
        if not text:
            return ''

        # タグを含む場合は誤マッチしやすいため、最初からマッチング不可とする
        if re.search(r"<[^>]+>", text):
            return 'マッピング不可'

        code = extract_equipment_code_only(text)
        if not code:
            m = re.search(r"[A-Za-z]{2}-\d{3}", text)
            code = m.group(0) if m else ""

        # 装置ID形式以外（プロセス等）は空表示
        try:
            if not re.match(r'^[A-Za-z]{2}-\d{3}$', code):
                return ''
        except Exception:
            return ''

        name_map = self._load_equipment_name_map()
        if not name_map:
            msg = getattr(self, '_equipment_name_map_missing_message', '')
            return msg or 'マッピングファイルなし'

        name = name_map.get(code)
        return name if name else '未登録'

    def _on_equip_process_item_changed(self, table: QTableWidget, item: Optional[QTableWidgetItem]) -> None:
        try:
            if item is None:
                return
            if table is None:
                return
            if item.column() != 0:
                return
            row = item.row()
            # mapping列は常に1
            mapping_item = table.item(row, 1)
            if mapping_item is None:
                mapping_item = QTableWidgetItem('')
                mapping_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                table.setItem(row, 1, mapping_item)

            mapping_item.setText(self._get_equipment_display_name(item.text()))
        except Exception:
            return

    def _iter_table_values_in_visual_order(self, table: QTableWidget) -> list[str]:
        values: list[str] = []
        if table is None:
            return values
        header = table.verticalHeader()
        for visual_row in range(table.rowCount()):
            logical_row = header.logicalIndex(visual_row) if header is not None else visual_row
            item = table.item(logical_row, 0)
            if item and item.text().strip():
                values.append(item.text().strip())
        return values

    def _create_equip_process_function_cell(self, table: QTableWidget, row: int) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        related_btn = QPushButton("関連カタログ")
        related_btn.setToolTip("関連データセットからリンク一覧を作成します")
        related_btn.clicked.connect(lambda _=False, r=row: self._on_equip_process_set_related_catalog(table, r))

        layout.addWidget(related_btn)
        layout.addStretch()
        return container

    def _set_table_row_text(self, table: QTableWidget, row: int, col: int, text: str) -> None:
        item = table.item(row, col)
        if item is None:
            item = QTableWidgetItem("")
            table.setItem(row, col, item)
        item.setText(text)

    def _on_equip_process_set_datetime(self, table: QTableWidget, row: int) -> None:
        try:
            text = self._prompt_datetime_text()
            if text is None:
                return
            self._set_table_row_text(table, row, 0, text)
        except Exception as exc:
            logger.error("日時ボタン処理で例外: %s", exc, exc_info=True)
            QMessageBox.critical(self, "日時", f"日時の適用に失敗しました\n{exc}")

    def _on_equip_process_set_related_catalog(self, table: QTableWidget, row: int) -> None:
        try:
            html = self._prompt_related_catalog_html()
            if html is None:
                return
            self._set_table_row_text(table, row, 0, html)
        except Exception as exc:
            logger.error("関連カタログボタン処理で例外: %s", exc, exc_info=True)
            QMessageBox.critical(self, "関連カタログ", f"関連カタログの適用に失敗しました\n{exc}")

    def _prompt_datetime_text(self) -> Optional[str]:
        dialog = QDialog(self)
        dialog.setWindowTitle("日時")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("現在日時（編集可）を適用します。"))

        dt_edit = QDateTimeEdit()
        dt_edit.setCalendarPopup(True)
        dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        dt_edit.setDateTime(QDateTime.currentDateTime())
        layout.addWidget(dt_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None

        return dt_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")

    def _load_related_catalog_candidates(self) -> Optional[list[dict]]:
        dataset_json_path = Path(get_dynamic_file_path(f"output/rde/data/datasets/{self.dataset_id}.json"))
        if not dataset_json_path.exists():
            QMessageBox.warning(self, "関連カタログ", f"データセット詳細JSONが見つかりません:\n{dataset_json_path}")
            return None

        try:
            dataset_payload = json.loads(dataset_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            QMessageBox.critical(self, "関連カタログ", f"データセット詳細JSONの解析に失敗しました:\n{dataset_json_path}\n{exc}")
            return None
        except OSError as exc:
            QMessageBox.critical(self, "関連カタログ", f"データセット詳細JSONを読み込めません:\n{dataset_json_path}\n{exc}")
            return None

        related_ids = extract_related_dataset_ids(dataset_payload)
        if not related_ids:
            QMessageBox.information(self, "関連カタログ", "関連データセットが見つかりませんでした。")
            return None

        public_root = get_public_data_portal_root_dir()
        public_json_path = find_latest_matching_file(
            public_root,
            (
                "output.json",
                "public_arim_data_details_*.json",
                "public_arim_data_*.json",
                "public_arim_data*.json",
            ),
        )
        if not public_json_path:
            QMessageBox.warning(self, "関連カタログ", f"公開データポータルJSONが見つかりません:\n{public_root}")
            return None

        try:
            public_payload = json.loads(public_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            QMessageBox.critical(self, "関連カタログ", f"公開データポータルJSONの解析に失敗しました:\n{public_json_path}\n{exc}")
            return None
        except OSError as exc:
            QMessageBox.critical(self, "関連カタログ", f"公開データポータルJSONを読み込めません:\n{public_json_path}\n{exc}")
            return None

        public_records = normalize_public_portal_records(public_payload)
        candidates = find_related_catalog_candidates(related_ids, public_records)
        if not candidates:
            QMessageBox.information(
                self,
                "関連カタログ",
                "公開データポータルJSON内に、関連データセットIDに一致するレコードが見つかりませんでした。",
            )
            return None

        logger.info(
            "関連カタログ候補 %d 件 (related=%d, public_file=%s)",
            len(candidates),
            len(related_ids),
            str(public_json_path),
        )
        return candidates

    def _prompt_related_catalog_html(self) -> Optional[str]:
        candidates = self._load_related_catalog_candidates()
        if not candidates:
            return None

        dialog = QDialog(self)
        dialog.setWindowTitle("関連カタログ")
        dialog.setModal(True)
        dialog.resize(760, 520)

        root = QVBoxLayout(dialog)
        root.addWidget(QLabel("関連カタログとして挿入するリンクを選択してください。"))

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("見出し:"))
        header_edit = QLineEdit("関連データカタログ")
        header_layout.addWidget(header_edit)
        root.addLayout(header_layout)

        tag_layout = QHBoxLayout()
        tag_layout.addWidget(QLabel("タグ:"))
        tag_edit = QLineEdit("h2")
        tag_edit.setMaximumWidth(80)
        tag_layout.addWidget(tag_edit)
        tag_layout.addWidget(QLabel("※h1〜h6以外は動作未確認"))
        tag_layout.addStretch()
        root.addLayout(tag_layout)

        body = QHBoxLayout()
        root.addLayout(body)

        # 左: チェックボックス一覧（スクロール）
        left = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(6, 6, 6, 6)
        list_layout.setSpacing(4)

        checkboxes: list[QCheckBox] = []
        for item in candidates:
            title = str(item.get("title") or item.get("id") or "")
            dataset_id = str(item.get("id") or "")
            url = item.get("detail_url") or item.get("url")

            cb = QCheckBox(title)
            cb.setChecked(True)
            cb.setProperty("dataset_id", dataset_id)
            if url:
                cb.setToolTip(str(url))
            checkboxes.append(cb)
            list_layout.addWidget(cb)

        list_layout.addStretch()
        scroll.setWidget(list_container)
        left.addWidget(scroll)
        body.addLayout(left, 1)

        # 右: HTMLプレビュー
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setMinimumWidth(360)
        body.addWidget(preview, 1)

        def selected_ids() -> set[str]:
            selected: set[str] = set()
            for cb in checkboxes:
                if cb.isChecked():
                    dataset_id = cb.property("dataset_id")
                    if isinstance(dataset_id, str) and dataset_id:
                        selected.add(dataset_id)
            return selected

        def update_preview() -> None:
            html = build_related_catalog_html(
                candidates,
                selected_ids=selected_ids(),
                header_text=header_edit.text(),
                header_tag=tag_edit.text(),
            )
            preview.setHtml(html)

        for cb in checkboxes:
            cb.toggled.connect(lambda _checked=False: update_preview())

        header_edit.textChanged.connect(lambda _text="": update_preview())
        tag_edit.textChanged.connect(lambda _text="": update_preview())

        update_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None

        return build_related_catalog_html(
            candidates,
            selected_ids=selected_ids(),
            header_text=header_edit.text(),
            header_tag=tag_edit.text(),
        )
    
    def _create_checkbox_group(self, field_name: str, label: str, max_selections: int = None) -> QWidget:
        """
        チェックボックスグループを作成
        
        Args:
            field_name: フィールド名（例: 't_a_code[]'）
            label: グループラベル
            max_selections: 最大選択数（Noneの場合は無制限）
        
        Returns:
            QWidget: チェックボックスグループウィジェット
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # メタデータから選択肢を取得
        if field_name not in self.metadata:
            logger.warning(f"メタデータに {field_name} が見つかりません")
            return container
        
        meta = self.metadata[field_name]
        
        # 現在の選択値を取得
        selected_values = []
        if field_name in self.form_data:
            field_data = self.form_data[field_name]
            if field_data['type'] == 'checkbox_array':
                selected_values = [v['value'] for v in field_data['values'] if v.get('checked', False)]
        
        # チェックボックスを作成
        checkboxes = []
        for opt in meta['options']:
            checkbox = QCheckBox(opt['label'] or opt['value'])
            checkbox.setProperty('value', opt['value'])
            if opt['value'] in selected_values:
                checkbox.setChecked(True)
            
            # 最大選択数の制限
            if max_selections is not None:
                checkbox.toggled.connect(lambda checked, cb=checkbox: self._on_checkbox_toggled(cb, checkboxes, max_selections))
            
            checkboxes.append(checkbox)
            layout.addWidget(checkbox)
        
        # ウィジェット辞書に保存
        self.field_widgets[field_name] = checkboxes
        
        return container
    
    def _on_checkbox_toggled(self, checkbox: 'QCheckBox', all_checkboxes: list, max_selections: int):
        """
        チェックボックストグル時の処理（最大選択数制限）
        
        Args:
            checkbox: トグルされたチェックボックス
            all_checkboxes: 全チェックボックスのリスト
            max_selections: 最大選択数
        """
        if not checkbox.isChecked():
            return
        
        # 選択されているチェックボックス数をカウント
        checked_count = sum(1 for cb in all_checkboxes if cb.isChecked())
        
        if checked_count > max_selections:
            # 最大選択数を超えた場合、このチェックボックスの選択を解除
            checkbox.setChecked(False)
            QMessageBox.warning(
                self,
                "選択数エラー",
                f"最大{max_selections}個まで選択できます。"
            )
    
    def _create_other_fields_group(self) -> QGroupBox:
        """その他の項目グループを作成"""
        group = QGroupBox("その他の項目")
        layout = QFormLayout()
        
        # 主要項目以外のフィールドを追加
        main_fields = {'t_mi_code', 't_license_level', 't_a_code', 't_code', 'mode', 'mode2', 'mode3', 'keyword', 'search_inst', 'search_license_level', 'search_status', 'page'}
        
        # ライセンス (t_license) - ドロップダウン
        if 't_license' in self.metadata:
            combo = QComboBox()
            combo.setMaximumWidth(400)
            current_value = self.form_data.get('t_license', {}).get('value', '')
            
            for opt in self.metadata['t_license']['options']:
                combo.addItem(opt['label'] or opt['value'], opt['value'])
                if opt['value'] == current_value:
                    combo.setCurrentText(opt['label'] or opt['value'])
            
            self.field_widgets['t_license'] = combo
            layout.addRow("ライセンス:", combo)
        
        # 重要技術領域（主） (main_mita_code_array[]) - ドロップダウン（複数選択不可）
        if 'main_mita_code_array[]' in self.metadata or 'sub_mita_code_array[]' in self.metadata:
            container = QWidget()
            grid = QGridLayout(container)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(6)

            # 主
            main_combo = QComboBox()
            main_combo.setMaximumWidth(400)
            main_combo.addItem("（選択なし）", "")
            main_selected_values: list[str] = []
            if 'main_mita_code_array[]' in self.form_data and self.form_data['main_mita_code_array[]']['type'] == 'checkbox_array':
                main_selected_values = [item['value'] for item in self.form_data['main_mita_code_array[]']['values'] if item['checked']]
            for opt in self.metadata.get('main_mita_code_array[]', {}).get('options', []):
                main_combo.addItem(opt['label'], opt['value'])
                if opt['value'] in main_selected_values:
                    main_combo.setCurrentText(opt['label'])
            self.field_widgets['main_mita_code_array[]'] = main_combo

            # 副
            sub_combo = QComboBox()
            sub_combo.setMaximumWidth(400)
            sub_combo.addItem("（選択なし）", "")
            sub_selected_values: list[str] = []
            if 'sub_mita_code_array[]' in self.form_data and self.form_data['sub_mita_code_array[]']['type'] == 'checkbox_array':
                sub_selected_values = [item['value'] for item in self.form_data['sub_mita_code_array[]']['values'] if item['checked']]
            for opt in self.metadata.get('sub_mita_code_array[]', {}).get('options', []):
                sub_combo.addItem(opt['label'], opt['value'])
                if opt['value'] in sub_selected_values:
                    sub_combo.setCurrentText(opt['label'])
            self.field_widgets['sub_mita_code_array[]'] = sub_combo

            # 自動設定ボタン（2行分の高さで右側に配置）
            auto_tech_btn = QPushButton("自動設定")
            auto_tech_btn.clicked.connect(self._on_auto_set_important_tech_areas)
            auto_tech_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                }}
            """)
            auto_tech_btn.setToolTip("報告書またはAIから重要技術領域を自動設定します")

            grid.addWidget(QLabel("（主）"), 0, 0)
            grid.addWidget(main_combo, 0, 1)
            grid.addWidget(QLabel("（副）"), 1, 0)
            grid.addWidget(sub_combo, 1, 1)
            grid.addWidget(auto_tech_btn, 0, 2, 2, 1)
            grid.setColumnStretch(1, 1)

            self._set_compact_autoset_button_width(auto_tech_btn)

            layout.addRow("重要技術領域:", container)
        
        # 横断技術領域 (mcta_code_array[]) - チェックボックスグループ（複数選択可）
        if 'mcta_code_array[]' in self.metadata:
            container = QWidget()
            outer = QGridLayout(container)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setHorizontalSpacing(8)
            outer.setVerticalSpacing(0)
            
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setMaximumHeight(120)
            #scroll.setMinimumHeight(120)
            
            scroll_content = QWidget()
            scroll_layout = QGridLayout(scroll_content)
            scroll_layout.setContentsMargins(0, 0, 0, 0)
            scroll_layout.setHorizontalSpacing(2)
            scroll_layout.setVerticalSpacing(0)
            
            # 既存の選択値を取得
            selected_values = []
            if 'mcta_code_array[]' in self.form_data and self.form_data['mcta_code_array[]']['type'] == 'checkbox_array':
                selected_values = [item['value'] for item in self.form_data['mcta_code_array[]']['values'] if item['checked']]
            
            checkboxes = []
            for idx, opt in enumerate(self.metadata['mcta_code_array[]']['options']):
                checkbox = QCheckBox(opt['label'])
                checkbox.setProperty('value', opt['value'])
                if opt['value'] in selected_values:
                    checkbox.setChecked(True)
                checkboxes.append(checkbox)

                row = idx // 4
                col = idx % 4
                scroll_layout.addWidget(checkbox, row, col)

            for col in range(4):
                scroll_layout.setColumnStretch(col, 1)
            scroll.setWidget(scroll_content)

            # 自動設定ボタン（2行分の高さで右側に配置）
            auto_cross_tech_btn = QPushButton("自動設定")
            auto_cross_tech_btn.clicked.connect(self._on_auto_set_cross_tech_areas)
            auto_cross_tech_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                }}
            """)
            auto_cross_tech_btn.setToolTip("報告書から横断技術領域を自動設定します")

            self._set_compact_autoset_button_width(auto_cross_tech_btn)

            outer.addWidget(scroll, 0, 0)
            outer.addWidget(auto_cross_tech_btn, 0, 1)
            outer.setColumnStretch(0, 1)

            self.field_widgets['mcta_code_array[]'] = checkboxes
            layout.addRow("横断技術領域:", container)
        
        # 設備分類 (mec_code_array[]) - サマリ表示 + 設定ダイアログ
        if 'mec_code_array[]' in self.metadata:
            options = self.metadata['mec_code_array[]']['options']
            selected_values: list[str] = []
            if 'mec_code_array[]' in self.form_data and self.form_data['mec_code_array[]']['type'] == 'checkbox_array':
                selected_values = [item['value'] for item in self.form_data['mec_code_array[]']['values'] if item['checked']]

            table_widget = FilterableCheckboxTable(
                field_name='mec_code_array[]',
                label='設備分類',
                options=options,
                selected_values=selected_values,
                max_height=220,
            )
            self.field_widgets['mec_code_array[]'] = table_widget
            self._park_hidden_editor(table_widget)

            row_widget, summary_label = self._create_summary_settings_row(
                field_key='mec_code_array[]',
                button_object_name='btn_settings_mec_code_array',
                on_open=lambda: self._open_checkbox_table_settings_dialog(
                    title='設備分類 設定ダイアログ',
                    field_key='mec_code_array[]',
                    autoset_title='設備分類 自動設定',
                    autoset_category='equipment',
                ),
            )
            layout.addRow("設備分類:", row_widget)
            self._summary_labels['mec_code_array[]'] = summary_label
            self._refresh_checkbox_summary('mec_code_array[]')
        
        # マテリアルインデックス (mmi_code_array[]) - サマリ表示 + 設定ダイアログ
        if 'mmi_code_array[]' in self.metadata:
            options = self.metadata['mmi_code_array[]']['options']
            selected_values: list[str] = []
            if 'mmi_code_array[]' in self.form_data and self.form_data['mmi_code_array[]']['type'] == 'checkbox_array':
                selected_values = [item['value'] for item in self.form_data['mmi_code_array[]']['values'] if item['checked']]

            table_widget = FilterableCheckboxTable(
                field_name='mmi_code_array[]',
                label='マテリアルインデックス',
                options=options,
                selected_values=selected_values,
                max_height=220,
            )
            self.field_widgets['mmi_code_array[]'] = table_widget
            self._park_hidden_editor(table_widget)

            row_widget, summary_label = self._create_summary_settings_row(
                field_key='mmi_code_array[]',
                button_object_name='btn_settings_mmi_code_array',
                on_open=lambda: self._open_checkbox_table_settings_dialog(
                    title='マテリアルインデックス 設定ダイアログ',
                    field_key='mmi_code_array[]',
                    autoset_title='マテリアルインデックス 自動設定',
                    autoset_category='material_index',
                ),
            )
            layout.addRow("マテリアルインデックス:", row_widget)
            self._summary_labels['mmi_code_array[]'] = summary_label
            self._refresh_checkbox_summary('mmi_code_array[]')
        
        # タグ (mt_code_array[]) - サマリ表示 + 設定ダイアログ
        if 'mt_code_array[]' in self.metadata:
            options = self.metadata['mt_code_array[]']['options']
            selected_values: list[str] = []
            if 'mt_code_array[]' in self.form_data and self.form_data['mt_code_array[]']['type'] == 'checkbox_array':
                selected_values = [item['value'] for item in self.form_data['mt_code_array[]']['values'] if item['checked']]

            table_widget = FilterableCheckboxTable(
                field_name='mt_code_array[]',
                label='タグ',
                options=options,
                selected_values=selected_values,
                max_height=220,
            )
            self.field_widgets['mt_code_array[]'] = table_widget
            self._park_hidden_editor(table_widget)

            row_widget, summary_label = self._create_summary_settings_row(
                field_key='mt_code_array[]',
                button_object_name='btn_settings_mt_code_array',
                on_open=lambda: self._open_checkbox_table_settings_dialog(
                    title='タグ 設定ダイアログ',
                    field_key='mt_code_array[]',
                    autoset_title='タグ 自動設定',
                    autoset_category='tag',
                ),
            )
            layout.addRow("タグ:", row_widget)
            self._summary_labels['mt_code_array[]'] = summary_label
            self._refresh_checkbox_summary('mt_code_array[]')
        
        # 装置・プロセス - サマリ表示 + 設定ダイアログ
        equip_process_table = self._create_editable_list_table(
            't_equip_process',
            '装置・プロセス',
            max_rows=20,
            visible_rows=5,
            function_column_label='機能',
            function_widget_factory=self._create_equip_process_function_cell,
        )
        self.field_widgets['t_equip_process'] = equip_process_table
        self._park_hidden_editor(equip_process_table)

        row_widget, summary_label = self._create_summary_settings_row(
            field_key='t_equip_process',
            button_object_name='btn_settings_equip_process',
            on_open=lambda: self._open_editable_table_settings_dialog(
                title='装置・プロセス 設定ダイアログ',
                field_key='t_equip_process',
                show_auto_equipment=True,
            ),
        )
        layout.addRow("装置・プロセス:", row_widget)
        self._summary_labels['t_equip_process'] = summary_label
        self._refresh_table_summary('t_equip_process')
        
        # 論文・プロシーディング - サマリ表示 + 設定ダイアログ（自動設定は現状非表示）
        paper_proceed_table = self._create_editable_list_table('t_paper_proceed', '論文・プロシーディング（DOI URL）', max_rows=20, visible_rows=5)
        self.field_widgets['t_paper_proceed'] = paper_proceed_table
        self._park_hidden_editor(paper_proceed_table)

        row_widget, summary_label = self._create_summary_settings_row(
            field_key='t_paper_proceed',
            button_object_name='btn_settings_paper_proceed',
            on_open=lambda: self._open_editable_table_settings_dialog(
                title='論文・プロシーディング 設定ダイアログ',
                field_key='t_paper_proceed',
                show_auto_equipment=False,
            ),
        )
        layout.addRow("論文・プロシーディング:", row_widget)
        self._summary_labels['t_paper_proceed'] = summary_label
        self._refresh_table_summary('t_paper_proceed')
        
        # 論文・プロシーディング 自動設定ボタン（将来復活する可能性あり、現在は非表示）
        # auto_publications_btn = QPushButton("🤖 論文・プロシーディング 自動設定")
        # auto_publications_btn.clicked.connect(self._on_auto_set_publications)
        # auto_publications_btn.setStyleSheet(f"""
        #     QPushButton {{
        #         background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
        #         color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
        #         padding: 6px 12px;
        #         border: none;
        #         border-radius: 4px;
        #         font-weight: bold;
        #     }}
        #     QPushButton:hover {{
        #         background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
        #     }}
        # """)
        # auto_publications_btn.setToolTip("報告書から論文・プロシーディング（DOI）を自動設定します")
        # layout.addRow("", auto_publications_btn)
        
        # その他のフィールド
        for key, field_data in self.form_data.items():
            # 主要項目と非表示フィールドはスキップ
            if key in main_fields or key.startswith('t_a_sub_code') or field_data['type'] == 'hidden':
                continue
            
            # 上記で処理済みのフィールドをスキップ
            if key in ['t_license', 'main_mita_code_array[]', 'sub_mita_code_array[]', 'mcta_code_array[]', 't_eqp_code_array[]', 'mi_code_array[]', 'tag_code_array[]']:
                continue
            
            # 装置・プロセスと論文・プロシーディングのフィールドもスキップ
            if key.startswith('t_equip_process') or key.startswith('t_paper_proceed'):
                continue
            
            label = field_data.get('label', key)
            
            if field_data['type'] == 'select':
                combo = QComboBox()
                for opt in field_data['options']:
                    combo.addItem(opt['text'], opt['value'])
                    if opt['selected']:
                        combo.setCurrentText(opt['text'])
                self.field_widgets[key] = combo
                layout.addRow(f"{label}:", combo)
            
            elif field_data['type'] in ['text', 'number', 'datetime-local', 'date', 'time']:
                value = field_data.get('value', '')
                if key in self._ZERO_DEFAULT_FIELDS and (value is None or str(value).strip() == ''):
                    value = '0'
                line_edit = QLineEdit(str(value))
                self.field_widgets[key] = line_edit
                layout.addRow(f"{label}:", line_edit)
            
            elif field_data['type'] == 'textarea':
                text_edit = QTextEdit()
                text_edit.setPlainText(field_data['value'])
                text_edit.setMaximumHeight(100)
                self.field_widgets[key] = text_edit
                layout.addRow(f"{label}:", text_edit)
            
            # その他のチェックボックス配列（既に上記で処理済み）
            elif field_data['type'] == 'checkbox_array':
                continue

        # ファイル数 / 全ファイルサイズ 自動設定ボタン
        file_count_widget = self.field_widgets.get('t_file_count')
        filesize_widget = self.field_widgets.get('t_meta_totalfilesize') or self.field_widgets.get('t_meta_totalfilesizeinthisversion')
        if file_count_widget and filesize_widget:
            auto_file_stats_btn = QPushButton("🤖 ファイル数/サイズ 自動設定")
            auto_file_stats_btn.clicked.connect(self._on_auto_set_file_stats)
            auto_file_stats_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                }}
            """)
            auto_file_stats_btn.setToolTip("データエントリー情報から総計（全ファイル）の統計を推定し、ファイル数と全ファイルサイズを更新します")
            layout.addRow("", auto_file_stats_btn)
            self.file_stats_auto_button = auto_file_stats_btn
        
        self._apply_form_layout_row_styling(layout)
        group.setLayout(layout)
        return group
    
    def _on_save(self):
        """保存処理（2段階: conf→rec）"""
        try:
            # 確認ダイアログ
            reply = QMessageBox.question(
                self,
                "修正確認",
                f"{self._build_environment_message()}\n\n"
                "データポータルのエントリを修正しますか?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # プログレスダイアログ
            progress = QProgressDialog("修正中...", None, 0, 2, self)
            progress.setWindowTitle("データカタログ修正")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setCancelButton(None)
            progress.setValue(0)
            QApplication.processEvents()
            
            # Step 1: 確認画面へ (mode3=conf)
            logger.info("[SAVE-STEP1] 確認画面へのPOST開始")
            progress.setLabelText("確認画面へ送信中...")
            QApplication.processEvents()
            
            conf_data = self._collect_form_data('conf')
            logger.info(f"[SAVE-STEP1] 送信データ: {len(conf_data)} fields")
            
            success, response = self.portal_client.post("main.php", data=conf_data)
            
            if not success:
                progress.close()
                logger.error(f"[SAVE-STEP1] 確認画面POST失敗: {response}")
                QMessageBox.critical(self, "エラー", f"確認画面への送信に失敗\n{response}")
                return
            
            # デバッグ保存
            if hasattr(response, 'text'):
                self._save_debug_response("edit_conf", response.text)
            
            logger.info("[SAVE-STEP1] 確認画面POST成功")
            
            # confレスポンスからhiddenフィールドを抽出
            conf_hidden_fields = self._parse_conf_response(response.text)
            logger.info(f"[SAVE-STEP1] 確認画面から抽出したフィールド数: {len(conf_hidden_fields)}")
            
            progress.setValue(1)
            
            # Step 2: 確定登録 (mode3=rec)
            logger.info("[SAVE-STEP2] 確定登録POST開始")
            progress.setLabelText("確定登録中...")
            QApplication.processEvents()
            
            # confレスポンスのhiddenフィールドを使用してrecデータを作成
            rec_data = {
                'mode': 'theme',
                'mode2': 'change',
                'mode3': 'rec',
                't_code': self.t_code,
                'keyword': self.dataset_id,
                'search_inst': '',
                'search_license_level': '',
                'search_status': '',
                'page': '1'
            }
            rec_data.update(conf_hidden_fields)
            logger.info(f"[SAVE-STEP2] 送信データ: {len(rec_data)} fields")
            
            success, response = self.portal_client.post("main.php", data=rec_data)
            
            progress.setValue(2)
            progress.close()
            
            if success:
                # デバッグ保存
                if hasattr(response, 'text'):
                    self._save_debug_response("edit_rec", response.text)
                
                logger.info("[SAVE-STEP2] 確定登録成功")
                QMessageBox.information(self, "成功", "データポータルの修正が完了しました")
                self.accept()
            else:
                logger.error(f"[SAVE-STEP2] 確定登録失敗: {response}")
                QMessageBox.critical(self, "エラー", f"確定登録に失敗\n{response}")
                
        except Exception as e:
            logger.error(f"保存エラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"保存エラー\n{e}")
    
    def _collect_form_data(self, mode3: str) -> dict:
        """フォームデータ収集"""
        post_data = {
            'mode': 'theme',
            'mode2': 'change',
            'mode3': mode3,
            't_code': self.t_code,
            'keyword': self.dataset_id,
            'search_inst': '',
            'search_license_level': '',
            'search_status': '',
            'page': '1'
        }
        
        # 非表示フィールドとチェックボックス配列
        for key, field_data in self.form_data.items():
            if field_data['type'] == 'hidden':
                post_data[key] = field_data['value']
            elif field_data['type'] == 'checkbox_array':
                # チェックされている値のみを配列として送信
                checked_values = [item['value'] for item in field_data['values'] if item['checked']]
                if checked_values:
                    post_data[key] = checked_values
        
        # 編集可能フィールド
        for key, widget in self.field_widgets.items():
            if isinstance(widget, FilterableCheckboxTable):
                # FilterableCheckboxTableからデータ取得
                checked = widget.get_selected_values()
                if checked:
                    post_data[key] = checked
                # 空の場合も空配列として送信（フォームクリア用）
                elif key in ['mmi_code_array[]', 'mt_code_array[]', 'mec_code_array[]']:
                    post_data[key] = []
            elif key in ['t_equip_process', 't_paper_proceed']:
                # QTableWidget（装置・プロセス、論文・プロシーディング）
                # サーバー側は20件固定を期待しているため、常に20件分送信
                if isinstance(widget, QTableWidget):
                    # 20行固定で送信（視覚順を維持し、空行も位置情報として保持）
                    header = widget.verticalHeader() if hasattr(widget, 'verticalHeader') else None
                    values: list[str] = []
                    for visual_row in range(20):
                        if visual_row >= widget.rowCount():
                            values.append("")
                            continue

                        logical_row = header.logicalIndex(visual_row) if header is not None else visual_row
                        item = widget.item(logical_row, 0)
                        values.append(item.text() if item is not None else "")

                    for i in range(1, 21):
                        post_data[f"{key}{i}"] = values[i - 1]
            elif isinstance(widget, QComboBox):
                value = widget.currentData()
                if value is not None and value != "":  # 空文字列は送信しない
                    # 配列フィールド（[]付き）の場合はリストとして送信
                    if key.endswith('[]'):
                        post_data[key] = [value]
                    else:
                        post_data[key] = value
            elif isinstance(widget, QLineEdit):
                text = widget.text()
                if key in self._ZERO_DEFAULT_FIELDS and (text is None or str(text).strip() == ''):
                    text = '0'
                post_data[key] = text
            elif isinstance(widget, QTextEdit):
                post_data[key] = widget.toPlainText()
            elif isinstance(widget, QButtonGroup):
                # ラジオボタングループ
                checked_button = widget.checkedButton()
                if checked_button:
                    post_data[key] = checked_button.property('value')
            elif isinstance(widget, list):
                # チェックボックスリスト（横断技術領域など）
                checked = []
                for cb in widget:
                    if cb.isChecked():
                        checked.append(cb.property('value'))
                if checked:
                    post_data[key] = checked
        
        return post_data
    
    def _parse_conf_response(self, html: str) -> dict:
        """
        確認画面のレスポンスからhiddenフィールドを抽出
        
        Args:
            html: 確認画面のHTML
        
        Returns:
            dict: hiddenフィールドのkey-valueマップ
        """
        try:
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html, 'html.parser')
            hidden_fields = {}
            
            # 全てのhidden inputを取得
            for hidden_input in soup.find_all('input', {'type': 'hidden'}):
                name = hidden_input.get('name')
                value = hidden_input.get('value', '')
                
                if name and name not in ['mode', 'mode2', 'mode3', 't_code', 'keyword', 'search_inst', 'search_license_level', 'search_status', 'page']:
                    # 配列フィールド（名前に[]が含まれる）の処理
                    if '[]' in name:
                        if name not in hidden_fields:
                            hidden_fields[name] = []
                        hidden_fields[name].append(value)
                    else:
                        hidden_fields[name] = value
            
            logger.info(f"[PARSE_CONF] 抽出したフィールド: {list(hidden_fields.keys())}")
            return hidden_fields
            
        except Exception as e:
            logger.error(f"[PARSE_CONF] 確認画面解析エラー: {e}", exc_info=True)
            return {}
    
    def _save_debug_response(self, step: str, html: str):
        """デバッグレスポンス保存"""
        try:
            from datetime import datetime
            from config.common import get_dynamic_file_path
            import os
            
            debug_dir = get_dynamic_file_path("output/data_portal_debug/edit")
            os.makedirs(debug_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{step}_{self.dataset_id}_{timestamp}.html"
            filepath = os.path.join(debug_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            
            logger.info(f"[DEBUG] 保存: {filepath}")
        except Exception as e:
            logger.warning(f"デバッグ保存失敗: {e}")
    
    def _on_auto_set_important_tech_areas(self):
        """重要技術領域（主・副）を自動設定"""
        try:
            from ..core.auto_setting_helper import (
                extract_important_tech_areas_from_report,
                suggest_important_tech_areas_with_ai,
                get_grant_number_from_dataset_json
            )
            from .auto_setting_dialog import AutoSettingDialog
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # 報告書ベースの候補取得関数
            def fetch_from_report(dataset_id: str) -> dict:
                return extract_important_tech_areas_from_report(dataset_id, grant_number)
            
            # AIベースの候補取得関数
            def fetch_from_ai(dataset_id: str) -> dict:
                return suggest_important_tech_areas_with_ai(dataset_id)
            
            # 自動設定ダイアログを表示
            dialog = AutoSettingDialog(
                title="重要技術領域 自動設定",
                field_name="重要技術領域（主・副）",
                dataset_id=self.dataset_id,
                report_fetcher=fetch_from_report,
                ai_fetcher=fetch_from_ai,
                metadata=self.metadata,
                parent=self
            )
            
            if dialog.exec_() == QDialog.Accepted:
                result = dialog.get_result()
                
                if result:
                    # 主を設定
                    if "main" in result and result["main"]:
                        main_combo = self.field_widgets.get('main_mita_code_array[]')
                        if main_combo and isinstance(main_combo, QComboBox):
                            # メタデータから対応するvalueを検索
                            main_value = self._find_metadata_value('main_mita_code_array[]', result["main"])
                            if main_value:
                                index = main_combo.findData(main_value)
                                if index >= 0:
                                    main_combo.setCurrentIndex(index)
                                    logger.info(f"重要技術領域（主）設定: {result['main']}")
                                else:
                                    # valueで見つからない場合、テキストで検索
                                    index = main_combo.findText(result["main"])
                                    if index >= 0:
                                        main_combo.setCurrentIndex(index)
                                        logger.info(f"重要技術領域（主）設定（テキスト一致）: {result['main']}")
                    
                    # 副を設定
                    if "sub" in result and result["sub"]:
                        sub_combo = self.field_widgets.get('sub_mita_code_array[]')
                        if sub_combo and isinstance(sub_combo, QComboBox):
                            # メタデータから対応するvalueを検索
                            sub_value = self._find_metadata_value('sub_mita_code_array[]', result["sub"])
                            if sub_value:
                                index = sub_combo.findData(sub_value)
                                if index >= 0:
                                    sub_combo.setCurrentIndex(index)
                                    logger.info(f"重要技術領域（副）設定: {result['sub']}")
                                else:
                                    # valueで見つからない場合、テキストで検索
                                    index = sub_combo.findText(result["sub"])
                                    if index >= 0:
                                        sub_combo.setCurrentIndex(index)
                                        logger.info(f"重要技術領域（副）設定（テキスト一致）: {result['sub']}")
                    
                    QMessageBox.information(
                        self,
                        "完了",
                        f"重要技術領域を設定しました。\n\n主: {result.get('main', '(なし)')}\n副: {result.get('sub', '(なし)')}"
                    )
        
        except Exception as e:
            logger.error(f"重要技術領域自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )
    
    def _find_metadata_value(self, field_name: str, label_or_value: str) -> Optional[str]:
        """
        メタデータからラベルまたは値に対応するvalueを検索
        
        Args:
            field_name: フィールド名（例: 'main_mita_code_array[]'）
            label_or_value: 検索するラベルまたは値
        
        Returns:
            Optional[str]: 対応するvalue（見つからない場合はNone）
        """
        if field_name not in self.metadata:
            return None
        
        for opt in self.metadata[field_name].get("options", []):
            if opt.get("value") == label_or_value or opt.get("label") == label_or_value:
                return opt.get("value")
        
        return None

    def _on_auto_set_cross_tech_areas(self):
        """横断技術領域を自動設定"""
        try:
            from ..core.auto_setting_helper import (
                extract_cross_tech_areas_from_report,
                get_grant_number_from_dataset_json
            )
            from .auto_setting_dialog import AutoSettingDialog
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # 報告書ベースの候補取得関数
            def fetch_from_report(dataset_id: str) -> dict:
                return extract_cross_tech_areas_from_report(dataset_id, grant_number)
            
            # 自動設定ダイアログを表示
            dialog = AutoSettingDialog(
                title="横断技術領域 自動設定",
                field_name="横断技術領域（主・副）",
                dataset_id=self.dataset_id,
                report_fetcher=fetch_from_report,
                ai_fetcher=None,  # AI推定は未対応
                metadata=self.metadata,
                parent=self
            )
            
            if dialog.exec_() == QDialog.Accepted:
                result = dialog.get_result()
                
                if result:
                    # 横断技術領域はチェックボックスリスト
                    checkboxes = self.field_widgets.get('mcta_code_array[]', [])
                    
                    if checkboxes:
                        # まず全てのチェックを外す
                        for cb in checkboxes:
                            cb.setChecked(False)
                        
                        # 主を設定
                        if "main" in result and result["main"]:
                            for cb in checkboxes:
                                if result["main"] in cb.text():
                                    cb.setChecked(True)
                                    logger.info(f"横断技術領域（主）設定: {result['main']}")
                                    break
                        
                        # 副を設定
                        if "sub" in result and result["sub"]:
                            for cb in checkboxes:
                                if result["sub"] in cb.text():
                                    cb.setChecked(True)
                                    logger.info(f"横断技術領域（副）設定: {result['sub']}")
                                    break
                        
                        QMessageBox.information(
                            self,
                            "完了",
                            f"横断技術領域を設定しました。\n\n主: {result.get('main', '(なし)')}\n副: {result.get('sub', '(なし)')}"
                        )
        
        except Exception as e:
            logger.error(f"横断技術領域自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )
    
    def _on_auto_set_equipment(self):
        """装置・プロセスを選択的置換ダイアログで自動設定"""
        try:
            from ..core.auto_setting_helper import (
                extract_equipment_from_report,
                get_grant_number_from_dataset_json
            )
            from .auto_setting_dialog import AutoSettingDialog
            from .selective_replacement_dialog import SelectiveReplacementDialog
            from classes.utils.facility_link_helper import extract_equipment_id
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # 報告書ベースの候補取得関数（装置リスト用）
            def fetch_equipment_from_report(dataset_id: str) -> dict:
                result = extract_equipment_from_report(dataset_id, grant_number)
                # 装置リストを文字列に変換（AutoSettingDialog表示用）
                equipment_list = result.get("equipment", []) if result else []
                text = "\n".join(equipment_list) if equipment_list else ""
                return {"equipment": equipment_list, "text": text}
            
            # 情報源選択ダイアログを表示
            info_dialog = AutoSettingDialog(
                title="装置・プロセス 自動設定",
                field_name="装置・プロセス",
                dataset_id=self.dataset_id,
                report_fetcher=fetch_equipment_from_report,
                ai_fetcher=None,  # AI推定は未対応
                metadata=self.metadata,
                parent=self
            )
            
            if info_dialog.exec_() != QDialog.Accepted:
                return  # キャンセルされた
            
            # 取得した候補を取り出す
            info_result = info_dialog.get_result()
            if not info_result or "equipment" not in info_result:
                QMessageBox.warning(
                    self,
                    "警告",
                    "装置・プロセスの候補が取得できませんでした。"
                )
                return
            
            equipment_list = info_result.get("equipment", [])
            
            # 既存のテーブル内容を取得
            table = self.field_widgets.get('t_equip_process')
            current_items = []
            if table and isinstance(table, QTableWidget):
                for i in range(table.rowCount()):
                    item = table.item(i, 0)
                    text = item.text() if item else ""
                    current_items.append(text)
            
            # 装置ID正規化関数（facility_link_helper使用）
            def equipment_normalizer(text: str) -> str:
                equip_id = extract_equipment_id(text)
                return equip_id.lower() if equip_id else text.strip().lower()
            
            # リンク化拡張機能（設備ID + 設備名）
            # NOTE: 要件により、リンク化ボタンは非表示（拡張ボタンを渡さない）
            extension_buttons = None
            
            # 選択的置換ダイアログ表示
            dialog = SelectiveReplacementDialog(
                title="装置・プロセス 選択的置換",
                field_prefix="t_equip_process",
                current_items=current_items,
                suggested_items=equipment_list,
                normalizer=equipment_normalizer,
                extension_buttons=extension_buttons,
                parent=self
            )
            
            if dialog.exec_() == QDialog.Accepted:
                result_data = dialog.get_result()
                final_items = result_data.get('final_items', [])
                
                # テーブルに適用（最大5行）
                if table and isinstance(table, QTableWidget):
                    # クリア
                    for i in range(table.rowCount()):
                        table.setItem(i, 0, QTableWidgetItem(""))
                    
                    # 要件: 適用してフォームに入力するのは装置コード(例: NM-005)のみ。装置名やリンクは挿入しない。
                    for i, equipment in enumerate(final_items[:5]):
                        text = str(equipment) if equipment is not None else ""
                        code_only = extract_equipment_code_only(text)
                        table.setItem(i, 0, QTableWidgetItem(code_only))
                    
                    logger.info(f"装置・プロセス適用: {len(final_items)}件（最大5件表示）")
                    QMessageBox.information(
                        self,
                        "完了",
                        f"装置・プロセスを{len(final_items)}件設定しました。"
                    )
        
        except Exception as e:
            logger.error(f"装置・プロセス自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )
    
    def _on_auto_set_equipment_legacy(self):
        """装置・プロセスを自動設定（旧実装・参考用）"""
        try:
            from ..core.auto_setting_helper import (
                extract_equipment_from_report,
                get_grant_number_from_dataset_json
            )
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # プログレスダイアログ
            progress = QProgressDialog("報告書から設備情報を取得中...", "中止", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()
            
            try:
                # 報告書から設備情報を取得
                result = extract_equipment_from_report(self.dataset_id, grant_number)
                
                progress.close()
                
                if result and result.get("equipment"):
                    equipment_list = result["equipment"]
                    # リンクタグ化準備
                    from classes.utils.facility_link_helper import (
                        find_latest_facilities_json,
                        lookup_facility_code_by_equipment_id,
                        lookup_facility_name_by_equipment_id,
                        extract_equipment_id,
                        build_equipment_anchor,
                        build_equipment_anchor_with_name,
                    )
                    latest_path = find_latest_facilities_json()
                    
                    # 装置・プロセステーブルに設定
                    table = self.field_widgets.get('t_equip_process')
                    if table and isinstance(table, QTableWidget):
                        # 既存の内容をクリア
                        for i in range(table.rowCount()):
                            table.setItem(i, 0, QTableWidgetItem(""))
                        
                        # 新しいデータを設定（最大5行）（設備名付き）
                        for i, equipment in enumerate(equipment_list[:5]):
                            text = str(equipment) if equipment is not None else ""
                            anchor_text = None
                            if latest_path is not None:
                                equip_id = extract_equipment_id(text)
                                if equip_id:
                                    code = lookup_facility_code_by_equipment_id(latest_path, equip_id)
                                    name = lookup_facility_name_by_equipment_id(latest_path, equip_id)
                                    if code and name:
                                        anchor_text = build_equipment_anchor_with_name(code, equip_id, name)
                            table.setItem(i, 0, QTableWidgetItem(anchor_text or text))
                        
                        logger.info(f"装置・プロセス設定(リンク化): {len(equipment_list)}件（最大5件表示） 最新JSON: {latest_path if latest_path else 'なし'}")
                        
                        QMessageBox.information(
                            self,
                            "完了",
                            f"装置・プロセスを設定しました。\n\n{len(equipment_list)}件の設備情報を取得しました。"
                        )
                    else:
                        QMessageBox.warning(
                            self,
                            "エラー",
                            "装置・プロセステーブルが見つかりませんでした。"
                        )
                else:
                    QMessageBox.warning(
                        self,
                        "情報なし",
                        "報告書に設備情報が登録されていません。"
                    )
            
            finally:
                progress.close()
        
        except Exception as e:
            logger.error(f"装置・プロセス自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )
    
    def _on_auto_set_publications(self):
        """論文・プロシーディングを選択的置換ダイアログで自動設定"""
        try:
            from ..core.auto_setting_helper import (
                extract_publications_from_report,
                get_grant_number_from_dataset_json
            )
            from .selective_replacement_dialog import SelectiveReplacementDialog
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # プログレスダイアログ
            progress = QProgressDialog("報告書から論文情報を取得中...", "中止", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()
            
            try:
                # 報告書から論文情報を取得
                result = extract_publications_from_report(self.dataset_id, grant_number)
                progress.close()
                
                # 結果に関わらずダイアログを表示（空の場合も含む）
                publications_list = result.get("publications", []) if result else []
                
                # 既存のテーブル内容を取得
                table = self.field_widgets.get('t_paper_proceed')
                current_items = []
                if table and isinstance(table, QTableWidget):
                    for i in range(table.rowCount()):
                        item = table.item(i, 0)
                        text = item.text() if item else ""
                        current_items.append(text)
                
                # DOI正規化関数
                def doi_normalizer(text: str) -> str:
                    """DOIを正規化（プロトコル除去・小文字化）"""
                    normalized = text.strip().lower()
                    # https://doi.org/ や http://dx.doi.org/ を除去
                    normalized = normalized.replace("https://doi.org/", "")
                    normalized = normalized.replace("http://doi.org/", "")
                    normalized = normalized.replace("http://dx.doi.org/", "")
                    normalized = normalized.replace("https://dx.doi.org/", "")
                    return normalized
                
                # 将来の拡張機能用（現在は空）
                extension_buttons = []
                
                # 選択的置換ダイアログ表示
                dialog = SelectiveReplacementDialog(
                    title="論文・プロシーディング 選択的置換",
                    field_prefix="t_paper_proceed",
                    current_items=current_items,
                    suggested_items=publications_list,
                    normalizer=doi_normalizer,
                    extension_buttons=extension_buttons,
                    parent=self
                )
                
                if dialog.exec_() == QDialog.Accepted:
                    result_data = dialog.get_result()
                    final_items = result_data.get('final_items', [])
                    
                    # テーブルに適用（最大20行）
                    if table and isinstance(table, QTableWidget):
                        # クリア
                        for i in range(table.rowCount()):
                            table.setItem(i, 0, QTableWidgetItem(""))
                        
                        # 設定
                        for i, publication in enumerate(final_items[:20]):
                            table.setItem(i, 0, QTableWidgetItem(publication))
                        
                        logger.info(f"論文・プロシーディング適用: {len(final_items)}件（最大20件表示）")
                        QMessageBox.information(
                            self,
                            "完了",
                            f"論文・プロシーディングを{len(final_items)}件設定しました。"
                        )
            
            except Exception as e:
                progress.close()
                raise
        
        except Exception as e:
            logger.error(f"論文・プロシーディング自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )
    
    def _on_auto_set_publications_legacy(self):
        """論文・プロシーディングを自動設定（旧実装・参考用）"""
        try:
            from ..core.auto_setting_helper import (
                extract_publications_from_report,
                get_grant_number_from_dataset_json
            )
            
            # 助成番号を取得
            grant_number = get_grant_number_from_dataset_json(self.dataset_id)
            
            if not grant_number:
                QMessageBox.warning(
                    self,
                    "警告",
                    "助成番号が取得できませんでした。\nデータセットのJSONファイルを確認してください。"
                )
                return
            
            # プログレスダイアログ
            progress = QProgressDialog("報告書から論文情報を取得中...", "中止", 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()
            
            try:
                # 報告書から論文情報を取得
                result = extract_publications_from_report(self.dataset_id, grant_number)
                
                progress.close()
                
                if result and result.get("publications"):
                    publications_list = result["publications"]
                    
                    # 論文・プロシーディングテーブルに設定
                    table = self.field_widgets.get('t_paper_proceed')
                    if table and isinstance(table, QTableWidget):
                        # 既存の内容をクリア
                        for i in range(table.rowCount()):
                            table.setItem(i, 0, QTableWidgetItem(""))
                        
                        # 新しいデータを設定（最大20行）
                        for i, publication in enumerate(publications_list[:20]):
                            table.setItem(i, 0, QTableWidgetItem(publication))
                        
                        logger.info(f"論文・プロシーディング設定: {len(publications_list)}件（最大20件表示）")
                        
                        QMessageBox.information(
                            self,
                            "完了",
                            f"論文・プロシーディングを設定しました。\n\n{len(publications_list)}件の論文情報を取得しました。"
                        )
                    else:
                        QMessageBox.warning(
                            self,
                            "エラー",
                            "論文・プロシーディングテーブルが見つかりませんでした。"
                        )
                else:
                    QMessageBox.warning(
                        self,
                        "情報なし",
                        "報告書に論文情報が登録されていません。"
                    )
            
            finally:
                progress.close()
        
        except Exception as e:
            logger.error(f"論文・プロシーディング自動設定エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"自動設定中にエラーが発生しました:\n{e}"
            )

    def _on_auto_set_file_stats(self):
        """ファイル数 / 全ファイルサイズを総計（全ファイル）の統計から自動設定"""
        try:
            summary = self._load_data_entry_summary()
            if not summary:
                QMessageBox.warning(
                    self,
                    "データなし",
                    "データエントリー情報からファイル統計を取得できませんでした。\n"
                    "基本情報タブでデータエントリーを取得済みか確認してください。"
                )
                return

            total = summary.get("total") or {}
            total_count = int(total.get("count", 0) or 0)
            total_bytes = int(total.get("bytes", 0) or 0)

            shared2 = summary.get("shared2") or {}
            shared2_count = int(shared2.get("count", 0) or 0)
            shared2_bytes = int(shared2.get("bytes", 0) or 0)

            nonshared = (summary.get("filetypes") or {}).get("NONSHARED_RAW") or {}
            nonshared_count = int(nonshared.get("count", 0) or 0)
            nonshared_bytes = int(nonshared.get("bytes", 0) or 0)

            formatted_total = format_size_with_bytes(total_bytes)
            formatted_shared2 = format_size_with_bytes(shared2_bytes)
            formatted_nonshared = format_size_with_bytes(nonshared_bytes)

            # fileTypeごとの短いラベル（dataset_dataentry_widget_minimal と同じ表示）
            file_type_labels = {
                "MAIN_IMAGE": "MAIN",
                "STRUCTURED": "STRCT",
                "NONSHARED_RAW": "NOSHARE",
                "RAW": "RAW",
                "META": "META",
                "ATTACHEMENT": "ATTACH",
                "THUMBNAIL": "THUMB",
                "OTHER": "OTHER",
            }
            filetypes = summary.get("filetypes") or {}
            breakdown_lines = []
            for ft, stats in filetypes.items():
                if not isinstance(stats, dict):
                    continue
                count = int(stats.get("count", 0) or 0)
                bytes_ = int(stats.get("bytes", 0) or 0)
                label = file_type_labels.get(ft, ft)
                breakdown_lines.append(f"- {label}: {count:,} 件 / {format_size_with_bytes(bytes_)}")
            breakdown_text = "\n".join(breakdown_lines) if breakdown_lines else "- (内訳なし)"

            message = (
                "データエントリー情報集計に基づく推定値です。\n\n"
                f"【総計】ファイル数: {total_count:,} 件\n"
                f"【総計】ファイルサイズ: {formatted_total}\n\n"
                "（参考）\n"
                f"【共用合計２】ファイル数: {shared2_count:,} 件\n"
                f"【共用合計２】ファイルサイズ: {formatted_shared2}\n\n"
                f"NONSHARED_RAW: {nonshared_count:,} 件 / {formatted_nonshared}\n\n"
                "【fileType別 内訳】\n"
                f"{breakdown_text}\n\n"
                "これらの値を適用しますか?"
            )
            reply = QMessageBox.question(
                self,
                "ファイル統計の適用",
                message,
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

            if self._apply_file_stats(shared2_count, shared2_bytes, total_bytes):
                QMessageBox.information(
                    self,
                    "適用完了",
                    "ファイル数と全ファイルサイズを更新しました。"
                )
        except Exception as exc:  # pragma: no cover
            logger.error(f"ファイル統計自動設定エラー: {exc}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"ファイル統計の取得中にエラーが発生しました:\n{exc}"
            )

    def _load_data_entry_summary(self, allow_fetch: bool = True):
        """Load dataEntry summary; optionally fetch dataEntry JSON when missing."""

        summary = get_data_entry_summary(self.dataset_id)
        if summary or not allow_fetch:
            return summary

        reply = QMessageBox.question(
            self,
            "データエントリー取得",
            "データエントリー情報が見つかりません。\n"
            "APIから最新情報を取得して推定値を計算しますか?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return None

        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(self)
        if not bearer_token:
            QMessageBox.warning(
                self,
                "認証エラー",
                "Bearer Tokenを取得できませんでした。ログイン状態を確認してください。"
            )
            return None

        progress = QProgressDialog("データエントリー情報を取得中...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        try:
            success = fetch_dataset_dataentry(self.dataset_id, bearer_token=bearer_token, force_refresh=True)
        finally:
            progress.close()

        if not success:
            QMessageBox.warning(
                self,
                "取得失敗",
                "データエントリー情報の取得に失敗しました。\n"
                "基本情報タブで先に取得できているか確認してください。"
            )
            return None

        return get_data_entry_summary(self.dataset_id)

    def _apply_file_stats(self, shared2_file_count: int, shared2_bytes: int, total_bytes: int) -> bool:
        """Apply calculated stats to corresponding widgets."""
        updated = False

        target_widgets = [
            # ファイル数: 共用合計２
            ('t_file_count', str(shared2_file_count)),
            # ファイルサイズ欄: 共用合計２
            ('t_meta_totalfilesizeinthisversion', str(shared2_bytes)),
            # 全ファイルサイズ欄: 総計
            ('t_meta_totalfilesize', str(total_bytes)),
        ]

        for field_name, value in target_widgets:
            widget = self.field_widgets.get(field_name)
            if isinstance(widget, QLineEdit):
                widget.setText(value)
                updated = True
            elif isinstance(widget, QTextEdit):
                widget.setPlainText(value)
                updated = True

        if not updated:
            QMessageBox.warning(
                self,
                "適用不可",
                "ファイル数または全ファイルサイズの入力フィールドが見つかりませんでした。"
            )

        return updated

    def _on_ai_suggest_checkbox_array(self, field_key: str, category: str):
        """AIで提案を取得し、チェックボックス配列に適用（設備/MI/タグ）"""
        try:
            from ..core.auto_setting_helper import fetch_ai_proposals_for_category

            widget = self.field_widgets.get(field_key)
            if not isinstance(widget, FilterableCheckboxTable):
                QMessageBox.warning(self, "エラー", "対象フィールドが見つかりませんでした")
                return

            # 適用モード
            mode = "append"
            if category == 'equipment' and hasattr(self, 'apply_mode_mec'):
                mode = 'replace' if self.apply_mode_mec.currentText() == '置換' else 'append'
            elif category == 'material_index' and hasattr(self, 'apply_mode_mmi'):
                mode = 'replace' if self.apply_mode_mmi.currentText() == '置換' else 'append'
            elif category == 'tag' and hasattr(self, 'apply_mode_mt'):
                mode = 'replace' if self.apply_mode_mt.currentText() == '置換' else 'append'

            # 取得中インジケータ
            progress = QProgressDialog("AIから候補を取得中...", None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()

            try:
                proposals = fetch_ai_proposals_for_category(self.dataset_id, category)
            finally:
                progress.close()

            if not proposals:
                QMessageBox.warning(self, "候補なし", "AIから候補を取得できませんでした")
                return

            # メタデータ上の有効なIDにフィルタ
            meta = self.metadata.get(field_key, {}).get('options', [])
            valid_ids = {str(opt.get('value')) for opt in meta}
            proposed_ids = [p.get('id') for p in proposals if p.get('id') in valid_ids]

            if not proposed_ids:
                QMessageBox.warning(self, "候補不一致", "AI候補はメタデータに一致しませんでした")
                return

            current = set(widget.get_selected_values())
            new_set = set(proposed_ids) if mode == 'replace' else (current.union(proposed_ids))

            widget.set_selected_values(sorted(new_set))

            QMessageBox.information(
                self,
                "AI適用完了",
                f"{len(proposed_ids)}件の候補を{ '置換' if mode=='replace' else '追記' }で適用しました。\n現在の選択数: {len(new_set)}"
            )
        except Exception as e:
            logger.error(f"AI提案適用エラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"AI提案の適用中にエラーが発生しました:\n{e}")

    def _open_checkbox_autoset_dialog(self, title: str, field_key: str, category: str):
        """チェックボックス配列用 自動設定ダイアログを開き、適用する"""
        try:
            from .auto_setting_checkbox_dialog import AutoSettingCheckboxDialog
            from ..core.auto_setting_helper import fetch_ai_proposals_for_category_with_debug

            dialog = AutoSettingCheckboxDialog(
                title=title,
                field_key=field_key,
                dataset_id=self.dataset_id,
                category=category,
                metadata=self.metadata,
                report_fetcher=None,
                ai_fetcher_debug=lambda dataset_id, cat: fetch_ai_proposals_for_category_with_debug(dataset_id, cat),
                parent=self,
            )

            if dialog.exec_() == QDialog.Accepted:
                result = dialog.get_result()
                if not result:
                    return
                mode = result.get('mode', 'append')
                ids = result.get('ids', [])

                widget = self.field_widgets.get(field_key)
                if not isinstance(widget, FilterableCheckboxTable):
                    QMessageBox.warning(self, "エラー", "対象フィールドが見つかりませんでした")
                    return

                current = set(widget.get_selected_values())
                new_set = set(ids) if mode == 'replace' else (current.union(ids))
                widget.set_selected_values(sorted(new_set))

                QMessageBox.information(
                    self,
                    "完了",
                    f"{len(ids)}件の候補を{ '置換' if mode=='replace' else '追記' }で適用しました。\n現在の選択数: {len(new_set)}"
                )
        except Exception as e:
            logger.error(f"自動設定ダイアログエラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"自動設定ダイアログ処理中にエラーが発生しました:\n{e}")

    def _park_hidden_editor(self, widget: QWidget) -> None:
        if not hasattr(self, '_hidden_editors_layout'):
            return
        try:
            self._hidden_editors_layout.addWidget(widget)
            widget.setVisible(False)
        except Exception:
            # 退避に失敗しても致命ではない
            pass

    def _format_selected_summary(self, names: list[str], max_items: int = 10) -> str:
        count = len(names)
        if count <= 0:
            return "(0件)"
        if count <= max_items:
            return f"{','.join(names)} ({count}件)"
        return f"{','.join(names[:max_items])},… ({count}件)"

    class _HeaderOnlyHTMLParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self._stack: list[str] = []
            self.headers: list[str] = []

        def handle_starttag(self, tag: str, attrs):
            self._stack.append(tag.lower())

        def handle_endtag(self, tag: str):
            tag = tag.lower()
            # pop until tag matches
            while self._stack:
                current = self._stack.pop()
                if current == tag:
                    break

        def handle_data(self, data: str):
            if not self._stack:
                return
            if self._stack[-1] in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                text = (data or "").strip()
                if text:
                    self.headers.append(text)

    def _extract_header_texts_from_html(self, html_text: str) -> list[str]:
        try:
            parser = self._HeaderOnlyHTMLParser()
            parser.feed(html_text or "")
            return [html_lib.unescape(t) for t in parser.headers if t.strip()]
        except Exception:
            return []

    def _load_equipment_name_map(self) -> dict[str, str]:
        if hasattr(self, "_equipment_name_map") and isinstance(getattr(self, "_equipment_name_map"), dict):
            return getattr(self, "_equipment_name_map")

        mapping: dict[str, str] = {}
        self._equipment_name_map_missing_message = ""

        candidate_rel_paths = [
            # 正式出力先
            "output/arim-site/equipment/merged_data2.json",
            # 想定外の配置（ユーザー環境で存在する場合に備える）
            "config/facilities/merged_data2.json",
            "setup/config/facilities/merged_data2.json",
        ]

        path: Optional[Path] = None
        for rel in candidate_rel_paths:
            try:
                p = Path(get_dynamic_file_path(rel))
                if p.exists() and p.is_file():
                    path = p
                    break
            except Exception:
                continue

        if path is None:
            self._equipment_name_map_missing_message = "マッピングファイルなし"
            self._equipment_name_map = mapping
            return mapping

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    equip_id = str(
                        item.get("設備ID")
                        or item.get("equipment_id")
                        or item.get("id")
                        or ""
                    ).strip()
                    name = str(
                        item.get("装置名_日")
                        or item.get("装置名")
                        or item.get("設備名称")
                        or item.get("装置名_英")
                        or item.get("equipment_name")
                        or item.get("name")
                        or ""
                    ).strip()
                    if equip_id and name:
                        mapping[equip_id] = name
            elif isinstance(data, dict):
                # dict形式の場合はキー/値をそのまま採用
                for k, v in data.items():
                    equip_id = str(k or "").strip()
                    name = str(v or "").strip()
                    if equip_id and name:
                        mapping[equip_id] = name
        except Exception:
            self._equipment_name_map_missing_message = "マッピングファイル読み込み失敗"
            mapping = {}

        if not mapping and not self._equipment_name_map_missing_message:
            self._equipment_name_map_missing_message = "マッピングデータなし"

        self._equipment_name_map = mapping
        return mapping

    def _format_equip_process_summary(self, raw_values: list[str], max_items: int = 10) -> str:
        # HTML混在対応: ヘッダタグのみを抽出して採用
        lines: list[str] = []
        for v in raw_values:
            text = (v or "").strip()
            if not text:
                continue
            if "<" in text and ">" in text:
                headers = self._extract_header_texts_from_html(text)
                for h in headers:
                    if h:
                        lines.append(h)
                continue
            lines.append(text)

        count = len(lines)
        if count <= 0:
            return "(0件)"

        name_map = self._load_equipment_name_map()
        missing_note = getattr(self, '_equipment_name_map_missing_message', '')
        formatted: list[str] = []
        id_pat = re.compile(r"^[A-Za-z]{2}-\d{3}$")
        for line in lines[:max_items]:
            if id_pat.match(line):
                name = name_map.get(line)
                if name:
                    formatted.append(f"{html_lib.escape(name)}&ensp;({html_lib.escape(line)})")
                else:
                    formatted.append(html_lib.escape(line) + (f"&ensp;({html_lib.escape(missing_note)})" if missing_note else ""))
            else:
                formatted.append(html_lib.escape(line))

        if count > max_items:
            formatted.append(f"…&ensp;({count}件)")
        else:
            formatted[-1] = f"{formatted[-1]}&ensp;({count}件)"

        return "<br>".join(formatted)

    def _refresh_checkbox_summary(self, field_key: str) -> None:
        label = self._summary_labels.get(field_key)
        widget = self.field_widgets.get(field_key)
        if label is None or not isinstance(widget, FilterableCheckboxTable):
            return

        selected = widget.get_selected_values()
        value_to_label = {
            str(opt.get('value')): (opt.get('label') or opt.get('value') or '')
            for opt in self.metadata.get(field_key, {}).get('options', [])
        }
        names = [str(value_to_label.get(str(v), v)) for v in selected]
        label.setText(self._format_selected_summary(names))

    def _refresh_table_summary(self, field_key: str) -> None:
        label = self._summary_labels.get(field_key)
        widget = self.field_widgets.get(field_key)
        if label is None or not isinstance(widget, QTableWidget):
            return

        values = self._iter_table_values_in_visual_order(widget)
        if field_key == 't_equip_process':
            label.setTextFormat(Qt.RichText)
            label.setText(self._format_equip_process_summary(values))
        else:
            label.setText(self._format_selected_summary(values))

    def _create_summary_settings_row(self, field_key: str, button_object_name: str, on_open: Callable[[], None]):
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        summary = QLabel("")
        summary.setWordWrap(True)
        summary.setObjectName(f"summary_{field_key}")
        if field_key == 't_equip_process':
            summary.setTextFormat(Qt.RichText)

        btn = QPushButton("設定")
        btn.setObjectName(button_object_name)
        btn.clicked.connect(on_open)

        h.addWidget(summary, 1)
        h.addWidget(btn, 0)
        return container, summary

    def _open_checkbox_table_settings_dialog(self, title: str, field_key: str, autoset_title: str, autoset_category: str) -> None:
        widget = self.field_widgets.get(field_key)
        if not isinstance(widget, FilterableCheckboxTable):
            QMessageBox.warning(self, "エラー", "対象フィールドが見つかりませんでした")
            return

        before = list(widget.get_selected_values())

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog_layout = QVBoxLayout(dialog)

        # 退避領域から取り外してダイアログへ移動
        try:
            self._hidden_editors_layout.removeWidget(widget)
        except Exception:
            pass
        widget.setParent(dialog)
        widget.setVisible(True)
        dialog_layout.addWidget(widget)

        auto_btn = QPushButton(f"🤖 {autoset_title}")
        auto_btn.setToolTip("専用ダイアログでAI提案を確認・適用します")
        auto_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
            }}
        """)
        auto_btn.clicked.connect(lambda: self._open_checkbox_autoset_dialog(autoset_title, field_key, autoset_category))
        dialog_layout.addWidget(auto_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)

        result = dialog.exec_()

        # ダイアログから退避領域へ戻す
        widget.setParent(self._hidden_editors)
        self._hidden_editors_layout.addWidget(widget)
        widget.setVisible(False)

        if result != QDialog.Accepted:
            widget.set_selected_values(before)
            return

        self._refresh_checkbox_summary(field_key)

    def _open_editable_table_settings_dialog(self, title: str, field_key: str, show_auto_equipment: bool) -> None:
        widget = self.field_widgets.get(field_key)
        if not isinstance(widget, QTableWidget):
            QMessageBox.warning(self, "エラー", "対象フィールドが見つかりませんでした")
            return

        before_texts: list[str] = []
        for row in range(widget.rowCount()):
            item = widget.item(row, 0)
            before_texts.append(item.text() if item else "")

        header = widget.verticalHeader()
        before_order = [header.logicalIndex(v) for v in range(widget.rowCount())] if header is not None else list(range(widget.rowCount()))

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog_layout = QVBoxLayout(dialog)

        # 装置・プロセスは名称列があるため幅を広く
        if field_key == 't_equip_process':
            dialog.setMinimumWidth(980)

        try:
            self._hidden_editors_layout.removeWidget(widget)
        except Exception:
            pass
        widget.setParent(dialog)
        widget.setVisible(True)
        dialog_layout.addWidget(widget)

        if show_auto_equipment:
            auto_equipment_btn = QPushButton("🤖 装置・プロセス 自動設定")
            auto_equipment_btn.clicked.connect(self._on_auto_set_equipment)
            auto_equipment_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_INFO_TEXT)};
                    padding: 6px 12px;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_INFO_BACKGROUND_HOVER)};
                }}
            """)
            auto_equipment_btn.setToolTip("報告書から利用した主な設備を自動設定します")
            dialog_layout.addWidget(auto_equipment_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)

        result = dialog.exec_()

        widget.setParent(self._hidden_editors)
        self._hidden_editors_layout.addWidget(widget)
        widget.setVisible(False)

        if result != QDialog.Accepted:
            # テキスト復元
            for row, text in enumerate(before_texts):
                item = widget.item(row, 0)
                if item is None:
                    item = QTableWidgetItem("")
                    widget.setItem(row, 0, item)
                item.setText(text)

            # 並び順（縦ヘッダ）復元
            try:
                vh = widget.verticalHeader()
                if vh is not None:
                    vh.setSectionsMovable(True)
                    for target_visual, logical in enumerate(before_order):
                        current_visual = vh.visualIndex(logical)
                        if current_visual != target_visual:
                            vh.moveSection(current_visual, target_visual)
            except Exception:
                pass

            # 装置名列の更新
            if field_key == 't_equip_process' and widget.columnCount() >= 2:
                for r in range(widget.rowCount()):
                    src = widget.item(r, 0)
                    mapping_item = widget.item(r, 1)
                    if mapping_item is None:
                        mapping_item = QTableWidgetItem('')
                        mapping_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                        widget.setItem(r, 1, mapping_item)
                    mapping_item.setText(self._get_equipment_display_name(src.text() if src else ''))
            return

        self._refresh_table_summary(field_key)
    
    def _on_facility_link_batch(self):
        """装置・プロセステーブル内の設備IDを一括リンク化"""
        try:
            from classes.utils.facility_link_helper import (
                find_latest_facilities_json,
                lookup_facility_code_by_equipment_id,
                lookup_facility_name_by_equipment_id,
                extract_equipment_id,
                build_equipment_anchor,
                build_equipment_anchor_with_name,
            )
            
            # テーブルウィジェット取得
            table = self.field_widgets.get('t_equip_process')
            if not table or not isinstance(table, QTableWidget):
                QMessageBox.warning(
                    self,
                    "警告",
                    "装置・プロセステーブルが見つかりません。"
                )
                return
            
            # 最新の設備マスターJSON取得
            latest_path = find_latest_facilities_json()
            if latest_path is None:
                QMessageBox.warning(
                    self,
                    "警告",
                    "設備マスターJSONファイルが見つかりません。\n基本情報タブで設備情報を取得してください。"
                )
                return
            
            # 各行をスキャンしてリンク化
            linked_count = 0
            unchanged_count = 0
            
            for i in range(table.rowCount()):
                item = table.item(i, 0)
                if not item:
                    continue
                
                text = item.text().strip()
                if not text:
                    continue
                
                # 既にアンカータグの場合はスキップ
                if text.startswith('<a ') and '</a>' in text:
                    unchanged_count += 1
                    continue
                
                # 設備ID抽出
                equip_id = extract_equipment_id(text)
                if equip_id:
                    # 設備コード・設備名取得
                    code = lookup_facility_code_by_equipment_id(latest_path, equip_id)
                    name = lookup_facility_name_by_equipment_id(latest_path, equip_id)
                    if code and name:
                        # リンクタグ生成（設備名付き）
                        anchor_text = build_equipment_anchor_with_name(code, equip_id, name)
                        table.setItem(i, 0, QTableWidgetItem(anchor_text))
                        linked_count += 1
                        logger.debug(f"設備リンク化: {equip_id} -> {code} ({name})")
                    else:
                        unchanged_count += 1
                        logger.debug(f"設備コードまたは設備名未取得: {equip_id}")
                else:
                    unchanged_count += 1
            
            # 結果通知
            if linked_count > 0:
                QMessageBox.information(
                    self,
                    "完了",
                    f"設備リンク化完了:\n{linked_count}件をリンク化しました。\n{unchanged_count}件は変更なし。"
                )
                logger.info(f"設備リンク化完了: {linked_count}件")
            else:
                QMessageBox.information(
                    self,
                    "完了",
                    "リンク化対象の設備IDが見つかりませんでした。"
                )
        
        except Exception as e:
            logger.error(f"設備リンク化エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"設備リンク化中にエラーが発生しました:\n{e}"
            )
    


