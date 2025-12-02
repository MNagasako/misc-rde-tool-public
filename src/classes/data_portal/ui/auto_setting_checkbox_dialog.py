"""
チェックボックス配列 自動設定ダイアログ（設備分類/マテリアルインデックス/タグ）

・情報源選択（報告書/AI）
・候補取得（AI）
・適用方法（追記/置換）選択
・AI問い合わせ内容（プロンプト）/受信JSONの表示

候補はIDリストとして適用（全件適用）。
"""
from typing import Callable, Dict, Any, List, Optional, Tuple
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QTextEdit, QMessageBox, QGroupBox,
    QComboBox, QListWidget, QListWidgetItem, QWidget
)
from qt_compat.core import Qt

from classes.theme import get_color, ThemeKey
from qt_compat.core import QThread, Signal
from classes.managers.log_manager import get_logger
from classes.dataset.ui.spinner_overlay import SpinnerOverlay

logger = get_logger("DataPortal.AutoSettingCheckboxDialog")


class AIProposalThread(QThread):
    finished_with_result = Signal(object)  # (proposals, prompt, raw)
    error_occurred = Signal(str)

    def __init__(self, dataset_id: str, category: str, fetcher: Callable[[str, str], Tuple[List[Dict[str, Any]], str, str]]):
        super().__init__()
        self.dataset_id = dataset_id
        self.category = category
        self.fetcher = fetcher
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            if self._stop:
                return
            proposals, prompt, raw = self.fetcher(self.dataset_id, self.category)
            if self._stop:
                return
            self.finished_with_result.emit({
                'proposals': proposals,
                'prompt': prompt,
                'raw': raw
            })
        except Exception as e:
            self.error_occurred.emit(str(e))


class AutoSettingCheckboxDialog(QDialog):
    def __init__(self,
                 title: str,
                 field_key: str,
                 dataset_id: str,
                 category: str,
                 metadata: Optional[Dict[str, Any]] = None,
                 report_fetcher: Optional[Callable[[str], Dict[str, Any]]] = None,
                 ai_fetcher_debug: Optional[Callable[[str, str], Tuple[List[Dict[str, Any]], str, str]]] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{title} - 自動設定")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)

        self.field_key = field_key
        self.dataset_id = dataset_id
        self.category = category
        self.metadata = metadata or {}
        self.report_fetcher = report_fetcher
        self.ai_fetcher_debug = ai_fetcher_debug

        self.selected_source = "ai"  # デフォルトAI（報告書機能は未実装の場合が多い）
        self.proposals: List[Dict[str, Any]] = []
        self.last_prompt: str = ""
        self.last_raw_json: str = ""

        # AIスレッド参照（初回fetch前に存在する必要あり）
        self.ai_thread: Optional[AIProposalThread] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 情報源選択
        source_group = QGroupBox("情報源選択")
        sl = QHBoxLayout()
        self.btn_group = QButtonGroup(self)
        self.report_radio = QRadioButton("報告書から取得")
        self.report_radio.setEnabled(bool(self.report_fetcher))
        self.report_radio.toggled.connect(self._on_source_changed)
        self.btn_group.addButton(self.report_radio, 0)

        self.ai_radio = QRadioButton("AIで推定")
        self.ai_radio.setChecked(True)
        self.ai_radio.toggled.connect(self._on_source_changed)
        self.btn_group.addButton(self.ai_radio, 1)

        sl.addWidget(self.report_radio)
        sl.addWidget(self.ai_radio)
        source_group.setLayout(sl)
        layout.addWidget(source_group)

        # 適用方法
        mode_group = QGroupBox("適用方法")
        ml = QHBoxLayout()
        ml.addWidget(QLabel("適用方法:"))
        self.apply_mode = QComboBox()
        # デフォルトを置換にする（順番: 置換 / 追記）
        self.apply_mode.addItems(["置換", "追記"])  # replace / append
        ml.addWidget(self.apply_mode)
        mode_group.setLayout(ml)
        layout.addWidget(mode_group)

        # 候補取得 + デバッグ表示ボタン
        action_row = QHBoxLayout()
        self.fetch_btn = QPushButton("候補を取得")
        self.fetch_btn.clicked.connect(self._on_fetch)
        self.view_prompt_btn = QPushButton("AI問い合わせ内容")
        self.view_prompt_btn.clicked.connect(self._on_view_prompt)
        self.view_prompt_btn.setEnabled(False)
        self.view_json_btn = QPushButton("AI受信JSON")
        self.view_json_btn.clicked.connect(self._on_view_json)
        self.view_json_btn.setEnabled(False)
        action_row.addWidget(self.fetch_btn)
        action_row.addStretch()
        action_row.addWidget(self.view_prompt_btn)
        action_row.addWidget(self.view_json_btn)
        layout.addLayout(action_row)

        # 候補表示（一覧）
        self.candidate_container = QWidget()
        cc_layout = QVBoxLayout(self.candidate_container)
        cc_layout.setContentsMargins(0, 0, 0, 0)
        self.candidate_list = QListWidget()
        self.candidate_list.setStyleSheet(f"QListWidget {{ background-color: {get_color(ThemeKey.INPUT_BACKGROUND)}; color: {get_color(ThemeKey.INPUT_TEXT)}; }}")
        cc_layout.addWidget(self.candidate_list)
        # スピナーオーバーレイ
        self.spinner_overlay = SpinnerOverlay(self.candidate_container, "AI候補取得中...")
        layout.addWidget(self.candidate_container)

        # 詳細表示
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("候補の詳細はここに表示されます")
        layout.addWidget(self.detail_text)

        # 説明
        info_box = QGroupBox("このダイアログについて")
        info_layout = QVBoxLayout()
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setPlainText(
            "このダイアログでは以下を行います:\n"
            "1) 情報源選択（現在はAIのみ有効）\n"
            "2) '候補を取得'でAIへ問い合わせ（最大60秒）\n"
            "3) 取得した候補IDをメタデータに照合\n"
            "4) 適用方法（置換/追記）を選択して全件適用\n"
            "5) 'AI問い合わせ内容'で送信したプロンプト, 'AI受信JSON'で生レスポンスを確認\n"
            "補足: 候補は全件一括適用です。個別選択機能は将来拡張可能です。"
        )
        info_text.setMaximumHeight(140)
        info_layout.addWidget(info_text)
        info_box.setLayout(info_layout)
        layout.addWidget(info_box)

        # 下部ボタン
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.cancel_btn = QPushButton("中止")
        self.cancel_btn.clicked.connect(self.reject)
        self.apply_btn = QPushButton("適用")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._on_apply)
        bottom.addWidget(self.cancel_btn)
        bottom.addWidget(self.apply_btn)
        layout.addLayout(bottom)

    def _on_source_changed(self):
        self.selected_source = "report" if self.report_radio.isChecked() else "ai"
        self.proposals = []
        self.last_prompt = ""
        self.last_raw_json = ""
        self.ai_thread: Optional[AIProposalThread] = None
        self.candidate_list.clear()
        self.detail_text.clear()
        self.apply_btn.setEnabled(False)
        self.view_prompt_btn.setEnabled(False)
        self.view_json_btn.setEnabled(False)

    def _on_fetch(self):
        try:
            if self.selected_source == "report":
                QMessageBox.information(self, "未実装", "報告書からの候補取得は未実装です")
                return
            if not self.ai_fetcher_debug:
                QMessageBox.warning(self, "未設定", "AI取得関数が設定されていません")
                return
            if self.ai_thread and self.ai_thread.isRunning():
                return

            # 非同期開始
            self.fetch_btn.setEnabled(False)
            self.apply_btn.setEnabled(False)
            self.view_prompt_btn.setEnabled(False)
            self.view_json_btn.setEnabled(False)
            self.spinner_overlay.start()

            self.ai_thread = AIProposalThread(self.dataset_id, self.category, self.ai_fetcher_debug)
            self.ai_thread.finished_with_result.connect(self._on_ai_thread_result)
            self.ai_thread.error_occurred.connect(self._on_ai_thread_error)
            self.ai_thread.start()
        except Exception as e:
            logger.error(f"候補取得（起動）エラー: {e}")
            QMessageBox.critical(self, "エラー", f"候補取得開始中にエラーが発生しました\n{e}")

    def _display_proposals(self):
        self.candidate_list.clear()
        lines = []
        for p in self.proposals:
            rank = p.get("rank")
            pid = p.get("id")
            label = p.get("label")
            reason = p.get("reason", "")
            text = f"{rank if rank is not None else '-'}: {label} ({pid})"
            item = QListWidgetItem(text)
            self.candidate_list.addItem(item)
            if reason:
                lines.append(f"・{label}（{pid}）: {reason}")
        if lines:
            self.detail_text.setPlainText("\n".join(lines))
        else:
            self.detail_text.setPlainText("候補の詳細はありません")

    def _on_view_prompt(self):
        if not self.last_prompt:
            QMessageBox.information(self, "情報", "プロンプトはありません")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("AI問い合わせ内容（プロンプト）")
        v = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(self.last_prompt)
        v.addWidget(te)
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(dlg.accept)
        v.addWidget(close_btn)
        dlg.resize(700, 500)
        dlg.exec_()

    def _on_view_json(self):
        if not self.last_raw_json:
            QMessageBox.information(self, "情報", "受信JSONはありません")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("AI受信JSON")
        v = QVBoxLayout(dlg)
        te = QTextEdit()
        te.setReadOnly(True)
        te.setPlainText(self.last_raw_json)
        v.addWidget(te)
        close_btn = QPushButton("閉じる")
        close_btn.clicked.connect(dlg.accept)
        v.addWidget(close_btn)
        dlg.resize(700, 500)
        dlg.exec_()

    def _on_apply(self):
        if not self.proposals:
            QMessageBox.warning(self, "警告", "候補がありません")
            return
        mode = 'replace' if self.apply_mode.currentText() == '置換' else 'append'
        ids = [str(p.get('id')) for p in self.proposals]
        self._applied = {"mode": mode, "ids": ids}
        self.accept()

    def get_result(self) -> Optional[Dict[str, Any]]:
        return getattr(self, "_applied", None)

    def _on_ai_thread_result(self, payload: Dict[str, Any]):
        try:
            self.spinner_overlay.stop()
            self.fetch_btn.setEnabled(True)
            self.view_prompt_btn.setEnabled(True)
            self.view_json_btn.setEnabled(True)
            self.last_prompt = payload.get('prompt', '')
            self.last_raw_json = payload.get('raw', '')
            proposals = payload.get('proposals', [])
            # メタデータフィルタ
            meta_opts = self.metadata.get(self.field_key, {}).get("options", [])
            valid_ids = {str(o.get("value")) for o in meta_opts}
            self.proposals = [p for p in proposals if str(p.get("id")) in valid_ids]
            self._display_proposals()
            self.apply_btn.setEnabled(bool(self.proposals))
        except Exception as e:
            logger.error(f"AI結果処理エラー: {e}")
            QMessageBox.critical(self, "エラー", f"AI結果処理中にエラーが発生しました\n{e}")

    def _on_ai_thread_error(self, message: str):
        self.spinner_overlay.stop()
        self.fetch_btn.setEnabled(True)
        QMessageBox.critical(self, "AIエラー", f"候補取得中にエラーが発生しました\n{message}")
