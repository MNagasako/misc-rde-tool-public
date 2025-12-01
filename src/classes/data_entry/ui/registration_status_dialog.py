import logging
from typing import List, Dict, Optional
from qt_compat.widgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem
from qt_compat.core import Qt

import classes.data_entry.core.registration_status_service as regsvc
from classes.dataset.ui.dataset_edit_widget import build_expanded_rows_for_dataset_entries

logger = logging.getLogger(__name__)

class RegistrationStatusDialog(QDialog):
    """登録状況を条件付きで表示するダイアログ。再取得ボタン付き。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登録状況の確認")
        self.conditions_label = QLabel("")
        self.refresh_button = QPushButton("再取得")
        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels([
            "データエントリーID", "名称", "登録状況ID", "登録状況ステータス", "登録開始日時", "リンク"
        ])
        layout = QVBoxLayout(self)
        ctrl = QHBoxLayout()
        ctrl.addWidget(self.conditions_label)
        ctrl.addStretch(1)
        ctrl.addWidget(self.refresh_button)
        layout.addLayout(ctrl)
        layout.addWidget(self.table)
        self.refresh_button.clicked.connect(self._on_refresh_clicked)
        self._data_items: List[Dict] = []
        self._dataset_name: Optional[str] = None
        self._last_entries: List[Dict] = []
        self._refresh_fn = None

    def set_conditions(self, text: str):
        self.conditions_label.setText(text)

    def set_sources(self, data_items: List[Dict], dataset_name: Optional[str], entries: List[Dict], refresh_fn):
        self._data_items = data_items
        self._dataset_name = dataset_name
        self._last_entries = entries
        self._refresh_fn = refresh_fn
        self._populate()

    def _populate(self):
        rows = build_expanded_rows_for_dataset_entries(self._data_items, self._dataset_name, self._last_entries)
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r.get('data_entry_id') or ''))
            self.table.setItem(row, 1, QTableWidgetItem(r.get('data_name') or ''))
            self.table.setItem(row, 2, QTableWidgetItem(r.get('reg_id') or ''))
            self.table.setItem(row, 3, QTableWidgetItem(r.get('reg_status') or ''))
            self.table.setItem(row, 4, QTableWidgetItem(r.get('start_time') or ''))
            # リンク列: 簡易表示（IDがある場合にURL文字列を設定）
            rid = r.get('reg_id') or ''
            url = f"https://rde-entry-arim.nims.go.jp/data-entry/datasets/entries/{rid}" if rid else ''
            self.table.setItem(row, 5, QTableWidgetItem(url))

    def _on_refresh_clicked(self):
        try:
            if callable(self._refresh_fn):
                entries = self._refresh_fn()
                if isinstance(entries, list):
                    self._last_entries = entries
                    self._populate()
        except Exception as e:
            logger.warning(f"[登録状況] 再取得で例外: {e}")


def _combine_entries(use_cache: bool = True) -> List[Dict]:
    """最新+全件キャッシュを統合して返す。"""
    latest = regsvc.fetch_latest(limit=100, use_cache=use_cache) or []
    all_entries = regsvc.fetch_all(use_cache=use_cache) or []
    by_id: Dict[str, Dict] = {}
    for e in all_entries:
        by_id[e.get('id')] = e
    for e in latest:
        by_id[e.get('id')] = e
    return list(by_id.values())


def show_status_dialog_for_single(parent, dataset_name: str, data_item: Dict, entries: Optional[List[Dict]] = None) -> RegistrationStatusDialog:
    """単体登録直後用: 最新1件相当の行＋総件数も表示。
    data_item は dataEntry の1アイテム（id/attributes/relationships を含むdict）。
    entries が未指定ならキャッシュから取得して使用。"""
    dlg = RegistrationStatusDialog(parent)
    # 条件テキスト
    dn = (data_item.get('attributes') or {}).get('name', '')
    owner_id = ((data_item.get('relationships') or {}).get('owner') or {}).get('data', {}).get('id', '')
    inst_id = ((data_item.get('relationships') or {}).get('instrument') or {}).get('data', {}).get('id', '')
    cond = f"条件: dataset={dataset_name}, dataName={dn}, owner={owner_id}, inst={inst_id}"
    dlg.set_conditions(cond)
    # entries 準備
    entries = entries if entries is not None else _combine_entries(use_cache=True)
    # データソース1件分でセット
    dlg.set_sources([data_item], dataset_name, entries, refresh_fn=lambda: _combine_entries(use_cache=False))
    dlg.setModal(True)
    dlg.resize(900, 400)
    dlg.show()
    return dlg


def show_status_dialog_for_batch(parent, dataset_name: str, data_items: List[Dict], entries: Optional[List[Dict]] = None) -> RegistrationStatusDialog:
    """一括登録完了用: 複数ファイルセットをまとめて表示。全て完了後に呼び出す。"""
    dlg = RegistrationStatusDialog(parent)
    cond = f"条件: dataset={dataset_name}, sets={len(data_items)}"
    dlg.set_conditions(cond)
    entries = entries if entries is not None else _combine_entries(use_cache=True)
    dlg.set_sources(data_items, dataset_name, entries, refresh_fn=lambda: _combine_entries(use_cache=False))
    dlg.setModal(True)
    dlg.resize(1000, 520)
    dlg.show()
    return dlg
