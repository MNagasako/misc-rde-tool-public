"""Public data portal fetch tab (no-login scraping)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from qt_compat.core import QThread, Signal
from qt_compat.widgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from classes.data_portal.util.public_output_paths import get_public_data_portal_root_dir
from classes.theme import ThemeKey, get_color
from classes.utils.data_portal_public import (
    PublicArimDataDetail,
    fetch_public_arim_data_details,
    migrate_public_data_portal_cache_dir,
    search_public_arim_data,
)

logger = logging.getLogger(__name__)


class _FetchThread(QThread):
    succeeded = Signal(int, str)
    failed = Signal(str)
    progress = Signal(int, int, str)

    def __init__(
        self,
        *,
        keyword: str,
        environment: str,
        timeout: int,
        start_page: int,
        end_page: int,
        max_workers: int,
        cache_enabled: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.keyword = keyword
        self.environment = environment
        self.timeout = timeout
        self.start_page = start_page
        self.end_page = end_page
        self.max_workers = max_workers
        self.cache_enabled = cache_enabled

    def run(self) -> None:  # noqa: D401
        try:
            # 旧キャッシュの *_raw 形式を新形式（英語キーdict）へ移行
            migrated, failed = migrate_public_data_portal_cache_dir(progress_callback=lambda c, t, m: self.progress.emit(c, t, m))
            if migrated or failed:
                self.progress.emit(0, 0, f"キャッシュ移行: migrated={migrated}, failed={failed}")

            self.progress.emit(0, 0, "検索リンク取得中...")

            def on_search_progress(current: int, total: int, message: str) -> None:
                self.progress.emit(current, total, message)

            links = search_public_arim_data(
                keyword=self.keyword,
                environment=self.environment,
                timeout=self.timeout,
                start_page=self.start_page,
                end_page=self.end_page,
                progress_callback=on_search_progress,
            )
            self.progress.emit(0, max(0, len(links)), f"リンク取得: {len(links)}件（detail取得開始）")

            out_dir = get_public_data_portal_root_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = out_dir / f"public_arim_data_details_{ts}.json"
            latest_path = out_dir / "output.json"

            # 中断してもファイルが残るよう、最初に空のJSONを作成
            records: list[dict] = []
            try:
                with out_path.open("w", encoding="utf-8") as handle:
                    json.dump(records, handle, ensure_ascii=False, indent=2)
                with latest_path.open("w", encoding="utf-8") as handle:
                    json.dump(records, handle, ensure_ascii=False, indent=2)
            except OSError:
                # 出力失敗でも取得処理自体は継続
                pass

            def on_detail_progress(current: int, total: int, message: str) -> None:
                self.progress.emit(current, total, message)

            def on_detail_item(detail: PublicArimDataDetail, done: int, total: int) -> None:
                record = asdict(detail)
                # Listing互換: url カラムが期待されるため detail_url を url にも入れる
                record.setdefault("url", record.get("detail_url", ""))
                records.append(record)

                # 中断しても途中結果が残るよう、逐次保存
                try:
                    with out_path.open("w", encoding="utf-8") as handle:
                        json.dump(records, handle, ensure_ascii=False, indent=2)
                    with latest_path.open("w", encoding="utf-8") as handle:
                        json.dump(records, handle, ensure_ascii=False, indent=2)
                except OSError:
                    pass

            # detailページの内容が本体なので、リンク先を取得して整形して格納する
            headers = None
            details: list[PublicArimDataDetail] = fetch_public_arim_data_details(
                links,
                environment=self.environment,
                timeout=self.timeout,
                headers=headers,
                max_workers=self.max_workers,
                cache_enabled=self.cache_enabled,
                progress_callback=on_detail_progress,
                item_callback=on_detail_item,
            )
            # 念のため、最終状態を保存（途中保存できていないケースの補完）
            if len(records) != len(details):
                records = []
                for detail in details:
                    record = asdict(detail)
                    record.setdefault("url", record.get("detail_url", ""))
                    records.append(record)
                try:
                    with out_path.open("w", encoding="utf-8") as handle:
                        json.dump(records, handle, ensure_ascii=False, indent=2)
                    with latest_path.open("w", encoding="utf-8") as handle:
                        json.dump(records, handle, ensure_ascii=False, indent=2)
                except OSError:
                    pass

            self.succeeded.emit(len(records), str(out_path))
        except Exception as exc:
            self.failed.emit(str(exc))


class PublicDataPortalFetchTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: _FetchThread | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        title = QLabel("<h2>📊 公開データポータル データ取得</h2>")
        layout.addWidget(title)

        settings_group = QGroupBox("取得設定")
        settings_layout = QVBoxLayout(settings_group)

        keyword_row = QHBoxLayout()
        keyword_row.addWidget(QLabel("検索キーワード:"))
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("空欄=全件（サイト仕様に依存）")
        keyword_row.addWidget(self.keyword_input, stretch=1)
        settings_layout.addLayout(keyword_row)

        env_row = QHBoxLayout()
        env_row.addWidget(QLabel("環境:"))
        self.env_combo = QComboBox()
        self.env_combo.addItem("本番 (nanonet.go.jp)", "production")
        self.env_combo.addItem("テスト (CloudFront)", "test")
        env_row.addWidget(self.env_combo)
        env_row.addStretch()
        settings_layout.addLayout(env_row)

        # ページ範囲
        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("取得ページ範囲:"))

        self.start_page_spin = QSpinBox()
        self.start_page_spin.setRange(1, 9999)
        self.start_page_spin.setValue(1)
        self.start_page_spin.setMinimumWidth(100)
        range_row.addWidget(self.start_page_spin)

        range_row.addWidget(QLabel("～"))

        self.end_page_spin = QSpinBox()
        self.end_page_spin.setRange(1, 9999)
        self.end_page_spin.setValue(9999)  # 大きい値はコア側で自動クランプ
        self.end_page_spin.setMinimumWidth(100)
        range_row.addWidget(self.end_page_spin)

        range_row.addWidget(QLabel("(ページ)"))
        range_row.addStretch()
        settings_layout.addLayout(range_row)

        # 並列数
        parallel_row = QHBoxLayout()
        parallel_row.addWidget(QLabel("並列数:"))
        self.max_workers_spin = QSpinBox()
        self.max_workers_spin.setRange(1, 20)
        self.max_workers_spin.setValue(4)
        self.max_workers_spin.setMinimumWidth(100)
        parallel_row.addWidget(self.max_workers_spin)
        parallel_row.addStretch()
        settings_layout.addLayout(parallel_row)

        # キャッシュ
        cache_row = QHBoxLayout()
        self.cache_checkbox = QCheckBox("キャッシュを使用（取得済みは再取得しない）")
        self.cache_checkbox.setChecked(False)
        cache_row.addWidget(self.cache_checkbox)
        cache_row.addStretch()
        settings_layout.addLayout(cache_row)

        layout.addWidget(settings_group)

        button_row = QHBoxLayout()
        self.fetch_all_button = QPushButton("📥 全件取得")
        self.fetch_all_button.setMinimumHeight(40)
        self.fetch_all_button.clicked.connect(self._on_fetch_all_clicked)
        button_row.addWidget(self.fetch_all_button)

        self.fetch_button = QPushButton("📥 取得開始")
        self.fetch_button.setMinimumHeight(40)
        self.fetch_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                font-weight: bold;
                border-radius: 5px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
            """
        )
        self.fetch_button.clicked.connect(self._on_fetch_clicked)
        button_row.addWidget(self.fetch_button)

        self.open_folder_button = QPushButton("📂 出力フォルダを開く")
        self.open_folder_button.setMinimumHeight(40)
        self.open_folder_button.clicked.connect(self._on_open_output_folder)
        button_row.addWidget(self.open_folder_button)

        button_row.addStretch()
        layout.addLayout(button_row)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(160)
        layout.addWidget(self.log_text)

        layout.addStretch()

    def _append_log(self, message: str) -> None:
        self.log_text.append(message)

    def _on_progress(self, current: int, total: int, message: str) -> None:
        # total<=0 は不確定進捗（検索中など）として扱う
        self.progress_bar.setVisible(True)
        if total <= 0:
            self.progress_bar.setRange(0, 0)
        else:
            # totalが変わる可能性があるため都度更新
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(max(0, min(current, total)))

        if message:
            self.status_label.setText(message)
            self._append_log(message)

    def _on_fetch_clicked(self) -> None:
        if self._thread and self._thread.isRunning():
            return

        keyword = self.keyword_input.text().strip()
        env = self.env_combo.currentData() or "production"
        start_page = int(self.start_page_spin.value())
        end_page = int(self.end_page_spin.value())
        max_workers = int(self.max_workers_spin.value())
        cache_enabled = bool(self.cache_checkbox.isChecked())

        self.fetch_button.setEnabled(False)
        self.fetch_all_button.setEnabled(False)
        self.status_label.setText("取得中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self._append_log(
            f"開始: keyword='{keyword}' env={env} pages={start_page}-{end_page} workers={max_workers} cache={cache_enabled}"
        )

        self._thread = _FetchThread(
            keyword=keyword,
            environment=env,
            timeout=30,
            start_page=start_page,
            end_page=end_page,
            max_workers=max_workers,
            cache_enabled=cache_enabled,
            parent=self,
        )
        self._thread.succeeded.connect(self._on_fetch_succeeded)
        self._thread.failed.connect(self._on_fetch_failed)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(lambda: self.fetch_button.setEnabled(True))
        self._thread.finished.connect(lambda: self.fetch_all_button.setEnabled(True))
        self._thread.start()

    def _on_fetch_all_clicked(self) -> None:
        # UI上は大きい値を入れておき、コア側で総ページ数にクランプする
        self.start_page_spin.setValue(1)
        self.end_page_spin.setValue(9999)
        self._on_fetch_clicked()

    def _on_fetch_succeeded(self, count: int, output_path: str) -> None:
        self.status_label.setText(f"✅ 完了: {count}件")
        if self.progress_bar.isVisible():
            self.progress_bar.setRange(0, max(0, count))
            self.progress_bar.setValue(max(0, count))
        self._append_log(f"完了: {count}件 -> {output_path}")

    def _on_fetch_failed(self, message: str) -> None:
        self.status_label.setText("❌ 失敗")
        self.progress_bar.setVisible(False)
        self._append_log(f"失敗: {message}")
        QMessageBox.warning(self, "公開データポータル取得", f"取得に失敗しました\n{message}")

    def _on_open_output_folder(self) -> None:
        try:
            out_dir = get_public_data_portal_root_dir()
            import os
            os.startfile(str(out_dir))  # noqa: S606
        except Exception as exc:
            QMessageBox.warning(self, "フォルダを開く", f"出力フォルダを開けませんでした\n{exc}")

    def refresh_theme(self) -> None:
        # 既存ReportFetchTab同様、必要最低限（ボタン等はsetStyleSheet済み）
        self.update()
