try:
    from qt_compat.widgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QLabel, QLineEdit, QComboBox
    from qt_compat.core import Qt
except Exception:
    from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QLabel, QLineEdit, QComboBox
    from PySide6.QtCore import Qt
import logging
from datetime import datetime, timezone, timedelta
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

import classes.data_entry.core.registration_status_service as regsvc
from classes.managers.token_manager import TokenManager

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

class RegistrationStatusWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登録状況")
        self.resize(1000, 600)
        layout = QVBoxLayout(self)

        # Controls
        ctrl = QHBoxLayout()
        self.btn_latest = QPushButton("最新100件を取得")
        self.btn_all = QPushButton("全件を取得 (オプション)")
        self.btn_clear = QPushButton("キャッシュ削除")
        self.lbl_summary = QLabel("")
        self.lbl_summary.setAlignment(Qt.AlignLeft)
        ctrl.addWidget(self.btn_latest)
        ctrl.addWidget(self.btn_all)
        ctrl.addWidget(self.btn_clear)
        ctrl.addWidget(self.lbl_summary)
        layout.addLayout(ctrl)

        # Filters row (per column + status)
        filters = QHBoxLayout()
        self.filter_start = QLineEdit(); self.filter_start.setPlaceholderText("開始時刻フィルタ")
        self.filter_data = QLineEdit(); self.filter_data.setPlaceholderText("データ名フィルタ")
        self.filter_dataset = QLineEdit(); self.filter_dataset.setPlaceholderText("データセットフィルタ")
        self.filter_status = QComboBox(); self.filter_status.addItem("(すべて)")
        self.filter_creator = QLineEdit(); self.filter_creator.setPlaceholderText("作成者フィルタ")
        self.filter_inst = QLineEdit(); self.filter_inst.setPlaceholderText("装置フィルタ")
        filters.addWidget(self.filter_start)
        filters.addWidget(self.filter_data)
        filters.addWidget(self.filter_dataset)
        filters.addWidget(self.filter_status)
        filters.addWidget(self.filter_creator)
        filters.addWidget(self.filter_inst)
        layout.addLayout(filters)

        self.cache_info_label = QLabel("キャッシュ情報: なし")
        self.cache_info_label.setAlignment(Qt.AlignLeft)
        self.cache_info_label.setWordWrap(True)
        layout.addWidget(self.cache_info_label)

        # Table
        self.table = QTableWidget(0, 8, self)
        self.table.setHorizontalHeaderLabels(["開始時刻","データ名","データセット","ステータス","作成者","装置","ID","リンク"])
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        # Signals
        self.btn_latest.clicked.connect(self.load_latest)
        self.btn_all.clicked.connect(self.load_all)
        self.btn_clear.clicked.connect(self.clear_cache)
        # Filter signals
        self.filter_start.textChanged.connect(self._apply_filters)
        self.filter_data.textChanged.connect(self._apply_filters)
        self.filter_dataset.textChanged.connect(self._apply_filters)
        self.filter_status.currentIndexChanged.connect(self._apply_filters)
        self.filter_creator.textChanged.connect(self._apply_filters)
        self.filter_inst.textChanged.connect(self._apply_filters)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            if regsvc.has_valid_cache():
                logger.info("[登録状況] キャッシュ有効を検知→自動表示")
                entries = regsvc.fetch_latest(limit=100, use_cache=True)
                if not entries:
                    entries = regsvc.fetch_all(default_chunk=5000, use_cache=True)
                self._populate(entries)
        except Exception as ex:
            logger.warning(f"[登録状況] 自動表示で例外: {ex}")
        finally:
            self.update_cache_info_label()

    def clear_cache(self):
        try:
            logger.info("[登録状況] キャッシュ削除ボタン押下")
            regsvc.clear_cache()
            self.lbl_summary.setText("キャッシュを削除しました")
            self.table.setRowCount(0)
        except Exception as ex:
            logger.exception(f"キャッシュ削除に失敗: {ex}")
            self.lbl_summary.setText("キャッシュ削除に失敗しました。ログをご確認ください。")
        finally:
            self.update_cache_info_label()

    def _populate(self, entries):
        self.table.setRowCount(0)
        statuses = set()
        for e in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(e.get('startTime') or ''))
            self.table.setItem(row, 1, QTableWidgetItem(e.get('dataName') or ''))
            self.table.setItem(row, 2, QTableWidgetItem(e.get('datasetName') or ''))
            self.table.setItem(row, 3, QTableWidgetItem(e.get('status') or ''))
            if e.get('status'):
                statuses.add(e.get('status'))
            self.table.setItem(row, 4, QTableWidgetItem(e.get('createdByName') or ''))
            ins = e.get('instrumentNameJa') or e.get('instrumentNameEn') or ''
            self.table.setItem(row, 5, QTableWidgetItem(ins))
            # ID列（リンクボタン対象のIDをそのまま表示）
            self.table.setItem(row, 6, QTableWidgetItem(e.get('id') or ''))
            btn = QPushButton("開く")
            btn.clicked.connect(lambda _=False, entry_id=e.get('id'): self._open_entry(entry_id))
            self.table.setCellWidget(row, 7, btn)
        status_counts = regsvc.count_by_status(entries)
        self.lbl_summary.setText(f"件数: {len(entries)} / ステータス: {status_counts}")
        # Update status filter
        current = self.filter_status.currentText()
        self.filter_status.blockSignals(True)
        self.filter_status.clear()
        self.filter_status.addItem("(すべて)")
        for s in sorted(statuses):
            self.filter_status.addItem(s)
        idx = self.filter_status.findText(current)
        if idx >= 0:
            self.filter_status.setCurrentIndex(idx)
        self.filter_status.blockSignals(False)

    def update_cache_info_label(self):
        try:
            metadata = regsvc.get_cache_metadata()
        except AttributeError:
            self.cache_info_label.setText("キャッシュ情報: 取得できません")
            return
        except Exception as exc:
            logger.warning("[登録状況] キャッシュ情報取得に失敗: %s", exc)
            self.cache_info_label.setText("キャッシュ情報: 取得に失敗しました")
            return

        if not metadata:
            self.cache_info_label.setText("キャッシュ情報: なし")
            return

        parts = []
        for info in metadata:
            label = "最新100件" if info.get("type") == "latest" else "全件"
            updated = info.get("updated_at")
            if isinstance(updated, datetime):
                updated_local = updated.astimezone(JST)
                timestamp = updated_local.strftime("%Y-%m-%d %H:%M:%S JST")
            else:
                timestamp = "時刻不明"
            count = info.get("count", 0)
            parts.append(f"{label}: {count}件 ({timestamp})")

        self.cache_info_label.setText("キャッシュ情報: " + " | ".join(parts))

    def _open_entry(self, entry_id: str):
        if not entry_id:
            return
        url = f"https://rde-entry-arim.nims.go.jp/data-entry/datasets/entries/{entry_id}"
        logger.info(f"[登録状況] エントリーをブラウザで開く: {url}")
        QDesktopServices.openUrl(QUrl(url))

    def _apply_filters(self):
        fs = {
            0: self.filter_start.text().strip().lower(),
            1: self.filter_data.text().strip().lower(),
            2: self.filter_dataset.text().strip().lower(),
            3: self.filter_status.currentText(),
            4: self.filter_creator.text().strip().lower(),
            5: self.filter_inst.text().strip().lower(),
        }
        rows = self.table.rowCount()
        for r in range(rows):
            visible = True
            for c in (0,1,2,4,5):
                item = self.table.item(r, c)
                val = (item.text() if item else '').lower()
                if fs[c] and fs[c] not in val:
                    visible = False
                    break
            if visible:
                if fs[3] and fs[3] != "(すべて)":
                    item = self.table.item(r, 3)
                    val = item.text() if item else ''
                    if val != fs[3]:
                        visible = False
            self.table.setRowHidden(r, not visible)

    def load_latest(self):
        try:
            logger.info("[登録状況] 最新100件取得ボタン押下")
            self.lbl_summary.setText("取得中… 最新100件を問い合わせています")
            logger.info("[登録状況] API呼び出し開始: fetch_latest(limit=100)")
            tm = TokenManager.get_instance()
            if not tm.get_access_token('rde.nims.go.jp'):
                # テストやキャッシュ利用のケースでも進めるため、早期returnはしない
                self.lbl_summary.setText("トークン未設定の可能性があります（必要に応じて左の『ログイン』をご利用ください）。続行して取得を試みます…")
                logger.warning("[登録状況] アクセストークン未検出: rde.nims.go.jp。続行して取得を試行します。")
            self.btn_latest.setEnabled(False)
            self.btn_all.setEnabled(False)
            entries = regsvc.fetch_latest(limit=100, use_cache=False)
            logger.debug(f"[登録状況] 取得件数: {len(entries)}")
            self._populate(entries)
            if len(entries) == 0:
                self.lbl_summary.setText("0件でした。認証エラーや権限不足の可能性があります。ログを確認してください。")
        except Exception as ex:
            logger.exception(f"最新取得に失敗: {ex}")
            self.lbl_summary.setText("最新取得に失敗しました。ログをご確認ください。")
        finally:
            self.btn_latest.setEnabled(True)
            self.btn_all.setEnabled(True)
            self.update_cache_info_label()

    def load_all(self):
        try:
            logger.info("[登録状況] 全件取得ボタン押下")
            self.lbl_summary.setText("取得中… 全件を問い合わせています")
            logger.info("[登録状況] API呼び出し開始: fetch_all(chunk=5000)")
            tm = TokenManager.get_instance()
            if not tm.get_access_token('rde.nims.go.jp'):
                # テストやキャッシュ利用のケースでも進めるため、早期returnはしない
                self.lbl_summary.setText("トークン未設定の可能性があります（必要に応じて左の『ログイン』をご利用ください）。続行して取得を試みます…")
                logger.warning("[登録状況] アクセストークン未検出: rde.nims.go.jp。続行して取得を試行します。")
            self.btn_latest.setEnabled(False)
            self.btn_all.setEnabled(False)
            entries = regsvc.fetch_all(default_chunk=5000, use_cache=False)
            logger.debug(f"[登録状況] 全件取得完了: {len(entries)}")
            self._populate(entries)
            if len(entries) == 0:
                self.lbl_summary.setText("0件でした。認証エラーや権限不足の可能性があります。ログを確認してください。")
        except Exception as ex:
            logger.exception(f"全件取得に失敗: {ex}")
            self.lbl_summary.setText("全件取得に失敗しました。ログをご確認ください。")
        finally:
            self.btn_latest.setEnabled(True)
            self.btn_all.setEnabled(True)
            self.update_cache_info_label()
