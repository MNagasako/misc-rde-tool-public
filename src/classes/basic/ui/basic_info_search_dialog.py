import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from qt_compat.widgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from classes.theme import ThemeKey, ThemeManager, get_color

logger = logging.getLogger(__name__)

PATTERN_MANUAL = "manual"
PATTERN_INSTITUTION = "institution_range"


@dataclass
class BasicInfoSearchSelection:
    """Stores the latest search preferences for the basic info dialog."""

    mode: str = "self"
    manual_keyword: str = ""
    keyword_batch: List[str] = field(default_factory=list)
    organization_id: str = ""
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    grant_prefix: str = "JPMXP12"

    def clone(self) -> "BasicInfoSearchSelection":
        return BasicInfoSearchSelection(
            mode=self.mode,
            manual_keyword=self.manual_keyword,
            keyword_batch=list(self.keyword_batch),
            organization_id=self.organization_id,
            start_year=self.start_year,
            end_year=self.end_year,
            grant_prefix=self.grant_prefix,
        )

    def display_keywords(self) -> List[str]:
        if self.keyword_batch:
            return list(self.keyword_batch)
        if self.manual_keyword:
            return [self.manual_keyword]
        return []


class BasicInfoSearchDialog(QDialog):
    """Dialog that lets users choose how basic info search should run."""

    def __init__(
        self,
        parent=None,
        default_keyword: str = "",
        previous_state: Optional[BasicInfoSearchSelection] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("基本情報取得(検索)の設定")
        self.setModal(True)
        self._theme_manager = ThemeManager.instance()
        self._selection: Optional[BasicInfoSearchSelection] = None
        self._state = self._resolve_initial_state(default_keyword, previous_state)

        self._self_radio = QRadioButton("自分のデータセット (ユーザー名検索)")
        self._search_radio = QRadioButton("検索条件を指定する")
        self._pattern_combo = QComboBox()
        self._stack = QStackedWidget()
        self._manual_input = QLineEdit()
        self._prefix_input = QLineEdit()
        self._org_input = QLineEdit()
        self._start_spin = QSpinBox()
        self._end_spin = QSpinBox()
        self._preview_label = QLabel()

        self._build_ui()
        self._apply_state(self._state)
        self._theme_manager.theme_changed.connect(self._apply_theme)
        self._apply_theme(self._theme_manager.get_mode())

    def _resolve_initial_state(
        self,
        default_keyword: str,
        previous_state: Optional[BasicInfoSearchSelection],
    ) -> BasicInfoSearchSelection:
        current_year = datetime.now().year
        if isinstance(previous_state, BasicInfoSearchSelection):
            base_state = previous_state.clone()
            if default_keyword and not base_state.manual_keyword:
                base_state.manual_keyword = default_keyword
            return base_state

        mode = "manual" if default_keyword else "self"
        return BasicInfoSearchSelection(
            mode=mode,
            manual_keyword=default_keyword,
            organization_id="TU",
            start_year=current_year,
            end_year=current_year,
            grant_prefix="JPMXP12",
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        description = QLabel(
            "基本情報取得(検索)で使用する対象を選択してください。\n"
            "• 自分のデータセット: RDEユーザー名で検索\n"
            "• 検索条件: キーワードまたは機関ID+年度で複数検索"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        radio_group = QButtonGroup(self)
        radio_group.addButton(self._self_radio)
        radio_group.addButton(self._search_radio)

        self._self_radio.toggled.connect(self._refresh_mode)
        layout.addWidget(self._self_radio)
        layout.addWidget(self._search_radio)

        # Pattern selector shown only for search mode
        pattern_row = QHBoxLayout()
        pattern_label = QLabel("検索パターン:")
        pattern_row.addWidget(pattern_label)
        self._pattern_combo.addItem("キーワードを直接指定", PATTERN_MANUAL)
        self._pattern_combo.addItem("機関ID + 年度レンジ", PATTERN_INSTITUTION)
        self._pattern_combo.currentIndexChanged.connect(self._refresh_mode)
        pattern_row.addWidget(self._pattern_combo, 1)
        layout.addLayout(pattern_row)

        # Manual panel
        manual_panel = QWidget()
        manual_layout = QVBoxLayout(manual_panel)
        manual_label = QLabel("検索キーワード:")
        manual_layout.addWidget(manual_label)
        self._manual_input.setPlaceholderText("例: JPMXP1222TU")
        manual_layout.addWidget(self._manual_input)
        manual_layout.addStretch()

        # Institution panel
        inst_panel = QWidget()
        inst_layout = QVBoxLayout(inst_panel)

        prefix_row = QHBoxLayout()
        prefix_label = QLabel("助成番号プレフィックス:")
        prefix_row.addWidget(prefix_label)
        self._prefix_input.setPlaceholderText("例: JPMXP12")
        prefix_row.addWidget(self._prefix_input)
        inst_layout.addLayout(prefix_row)

        org_row = QHBoxLayout()
        org_label = QLabel("機関ID:")
        org_row.addWidget(org_label)
        self._org_input.setPlaceholderText("例: TU")
        self._org_input.setMaxLength(6)
        org_row.addWidget(self._org_input)
        inst_layout.addLayout(org_row)

        year_row = QHBoxLayout()
        year_label = QLabel("年度範囲:")
        year_row.addWidget(year_label)
        self._start_spin.setRange(2015, 2100)
        self._end_spin.setRange(2015, 2100)
        year_row.addWidget(self._start_spin)
        year_row.addWidget(QLabel("〜"))
        year_row.addWidget(self._end_spin)
        inst_layout.addLayout(year_row)

        self._preview_label.setWordWrap(True)
        inst_layout.addWidget(self._preview_label)
        inst_layout.addStretch()

        self._stack.addWidget(manual_panel)
        self._stack.addWidget(inst_panel)
        layout.addWidget(self._stack)

        button_row = QHBoxLayout()
        button_row.addStretch()
        ok_button = QPushButton("実行")
        cancel_button = QPushButton("キャンセル")
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(ok_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        self._manual_input.textChanged.connect(self._update_preview)
        self._prefix_input.textChanged.connect(self._update_preview)
        self._org_input.textChanged.connect(self._update_preview)
        self._start_spin.valueChanged.connect(self._update_preview)
        self._end_spin.valueChanged.connect(self._update_preview)

    def _apply_state(self, state: BasicInfoSearchSelection) -> None:
        if state.mode == "self":
            self._self_radio.setChecked(True)
        else:
            self._search_radio.setChecked(True)

        if state.mode == PATTERN_INSTITUTION:
            index = self._pattern_combo.findData(PATTERN_INSTITUTION)
            if index >= 0:
                self._pattern_combo.setCurrentIndex(index)
        else:
            self._pattern_combo.setCurrentIndex(self._pattern_combo.findData(PATTERN_MANUAL))

        self._manual_input.setText(state.manual_keyword)
        self._prefix_input.setText(state.grant_prefix)
        self._org_input.setText(state.organization_id)
        if state.start_year:
            self._start_spin.setValue(state.start_year)
        if state.end_year:
            self._end_spin.setValue(state.end_year)

        self._refresh_mode()
        self._update_preview()

    def _refresh_mode(self) -> None:
        is_search = self._search_radio.isChecked()
        self._pattern_combo.setEnabled(is_search)
        self._stack.setVisible(is_search)

        pattern = self._pattern_combo.currentData()
        index = 0 if pattern == PATTERN_MANUAL else 1
        self._stack.setCurrentIndex(index)
        self._update_preview()

    def _update_preview(self) -> None:
        if not self._search_radio.isChecked():
            self._preview_label.clear()
            return

        pattern = self._pattern_combo.currentData()
        if pattern != PATTERN_INSTITUTION:
            self._preview_label.setText("キーワードは手動入力を使用します。")
            return

        prefix = self._prefix_input.text().strip()
        org_id = self._org_input.text().strip().upper()
        start_year = self._start_spin.value()
        end_year = self._end_spin.value()

        if not prefix or not org_id:
            self._preview_label.setText("キーワード例: ---")
            return

        preview_end = min(end_year, start_year + 2)
        samples = _generate_keywords(prefix, org_id, start_year, preview_end)
        display = ", ".join(samples[:3]) if samples else "---"
        self._preview_label.setText(f"キーワード例: {display}")

    def _apply_theme(self, *_args) -> None:
        panel_bg = get_color(ThemeKey.PANEL_INFO_BACKGROUND)
        panel_border = get_color(ThemeKey.PANEL_INFO_BORDER)
        text_color = get_color(ThemeKey.TEXT_PRIMARY)
        input_border = get_color(ThemeKey.BORDER_INFO)
        highlight = get_color(ThemeKey.BUTTON_INFO_BACKGROUND)

        self.setStyleSheet("")
        for widget in [self._manual_input, self._prefix_input, self._org_input]:
            widget.setStyleSheet(
                f"QLineEdit {{ border: 1px solid {input_border}; border-radius: 4px; padding: 4px; }}"
                f" QLineEdit:focus {{ border-color: {highlight}; }}"
            )
        for spin in [self._start_spin, self._end_spin]:
            spin.setStyleSheet(
                f"QSpinBox {{ border: 1px solid {input_border}; border-radius: 4px; padding: 2px; }}"
            )

        self._preview_label.setStyleSheet(
            f"padding: 6px; border: 1px dashed {panel_border}; background-color: {panel_bg}; color: {text_color};"
        )

    def accept(self) -> None:  # type: ignore[override]
        selection = self._collect_selection()
        if not selection:
            return
        self._selection = selection
        super().accept()

    def _collect_selection(self) -> Optional[BasicInfoSearchSelection]:
        if self._self_radio.isChecked():
            return BasicInfoSearchSelection(mode="self")

        pattern = self._pattern_combo.currentData()
        if pattern == PATTERN_MANUAL:
            keyword = self._manual_input.text().strip()
            if not keyword:
                QMessageBox.warning(self, "入力不足", "検索キーワードを入力してください。")
                return None
            return BasicInfoSearchSelection(mode=PATTERN_MANUAL, manual_keyword=keyword)

        prefix = self._prefix_input.text().strip()
        org_id = self._org_input.text().strip().upper()
        start_year = self._start_spin.value()
        end_year = self._end_spin.value()

        if not prefix:
            QMessageBox.warning(self, "入力不足", "助成番号プレフィックスを入力してください。")
            return None
        if not org_id:
            QMessageBox.warning(self, "入力不足", "機関IDを入力してください。")
            return None
        if start_year > end_year:
            QMessageBox.warning(self, "入力エラー", "年度範囲の指定が正しくありません。")
            return None

        keywords = _generate_keywords(prefix, org_id, start_year, end_year)
        if not keywords:
            QMessageBox.warning(self, "入力エラー", "生成されたキーワードがありません。")
            return None

        return BasicInfoSearchSelection(
            mode=PATTERN_INSTITUTION,
            keyword_batch=keywords,
            organization_id=org_id,
            start_year=start_year,
            end_year=end_year,
            grant_prefix=prefix,
        )

    def get_selection(self) -> Optional[BasicInfoSearchSelection]:
        return self._selection


def _generate_keywords(prefix: str, org_id: str, start_year: int, end_year: int) -> List[str]:
    keywords: List[str] = []
    normalized_prefix = prefix.strip()
    normalized_org = org_id.strip().upper()
    if not normalized_prefix or not normalized_org:
        return keywords

    for year in range(start_year, end_year + 1):
        suffix = f"{year % 100:02d}"
        keywords.append(f"{normalized_prefix}{suffix}{normalized_org}")
    return keywords


def prompt_basic_info_search_options(
    parent,
    default_keyword: str = "",
    previous_state: Optional[BasicInfoSearchSelection] = None,
) -> Optional[BasicInfoSearchSelection]:
    """Show the dialog and return the chosen selection."""

    dialog = BasicInfoSearchDialog(parent, default_keyword=default_keyword, previous_state=previous_state)
    result = dialog.exec()
    if result == QDialog.Accepted:
        selection = dialog.get_selection()
        if selection:
            logger.debug("基本情報検索ダイアログ選択: mode=%s words=%s", selection.mode, selection.display_keywords())
        return selection
    return None
