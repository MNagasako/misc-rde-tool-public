from __future__ import annotations

try:
    from qt_compat.widgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QHBoxLayout, QLineEdit
    from qt_compat.core import Signal
except ImportError:
    from src.qt_compat.widgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QHBoxLayout, QLineEdit
    from src.qt_compat.core import Signal

from classes.config.core.supported_formats_service import copy_to_input, parse_and_save
from classes.theme import get_color, ThemeKey
from classes.theme import ThemeManager
from config.common import get_dynamic_file_path


class UploadXlsxTab(QWidget):
    """設定ウィジェット用: XLSXアップロードタブ（最小機能）。

    既存機能へ干渉しない独立ウィジェット。ファイル選択とパス表示のみ。
    実際の保存・解析連携は今後の拡張で追加する。
    """

    # 解析完了時に外部へ通知するシグナル（entries: List[SupportedFileFormatEntry]）
    entriesParsed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("データ構造化対応リスト（XLSX）")
        layout.addWidget(title)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("ファイルが選択されていません")

        pick_btn = QPushButton("ファイルを選択")
        pick_btn.clicked.connect(self._pick_file)

        # 明示的なアップロード/解析ボタン
        self.upload_btn = QPushButton("解析を実行")
        self.upload_btn.setEnabled(False)
        self.upload_btn.clicked.connect(self._upload_and_parse)
        
        # リセットボタン
        self.reset_btn = QPushButton("解析結果をリセット")
        self.reset_btn.clicked.connect(self._reset_data)

        # ステータス表示（進行状況）
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_INFO)}; font-weight: bold;"
        )
        layout.addWidget(self.progress_label)
        
        # 結果表示（成功/失敗）
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        row = QHBoxLayout()
        row.addWidget(self.path_edit)
        row.addWidget(pick_btn)
        row.addWidget(self.upload_btn)
        row.addWidget(self.reset_btn)
        layout.addLayout(row)

        note = QLabel("※ XLSXを選択後、[解析を実行]を押すと、装置IDや拡張子情報を抽出します。")
        note.setWordWrap(True)
        layout.addWidget(note)

        try:
            ThemeManager.instance().theme_changed.connect(self.refresh_theme)
        except Exception:
            pass

    def refresh_theme(self, *_):
        try:
            self.progress_label.setStyleSheet(
                f"color: {get_color(ThemeKey.TEXT_INFO)}; font-weight: bold;"
            )
        except Exception:
            pass

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "XLSXを選択", "", "Excel Files (*.xlsx *.xls)")
        if not path:
            return
        self.path_edit.setText(path)
        self.upload_btn.setEnabled(True)

    def _upload_and_parse(self):
        src = self.path_edit.text().strip()
        if not src:
            self.result_label.setText("⚠ ファイルが選択されていません")
            self.result_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_WARNING)};")
            return
        
        self.progress_label.setText("⏳ 処理中...")
        self.result_label.setText("")
        self.upload_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        
        try:
            # 取り込み（input/arim配下へコピー）
            self.progress_label.setText("⏳ ファイルを取り込み中...")
            saved = copy_to_input(src)
            
            self.progress_label.setText("⏳ 解析中...")
            entries = parse_and_save(saved)
            
            self.progress_label.setText("")
            self.result_label.setText(f"✅ 解析完了: {len(entries)}件のエントリを抽出しました。")
            self.result_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SUCCESS)}; font-weight: bold;")
            self.entriesParsed.emit(entries)
        except Exception as ex:
            self.progress_label.setText("")
            self.result_label.setText(f"❌ 解析失敗: {ex}")
            self.result_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
            import traceback
            traceback.print_exc()
        finally:
            self.upload_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
    
    def _reset_data(self):
        """解析結果をリセット（JSONファイル削除）"""
        try:
            import os, pathlib
            json_path = pathlib.Path(get_dynamic_file_path("output/supported_formats.json"))
            if json_path.exists():
                os.remove(json_path)
                self.result_label.setText("✅ 解析結果をリセットしました。")
                self.result_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SUCCESS)};")
                self.path_edit.clear()
                # 一覧もクリア
                self.entriesParsed.emit([])
            else:
                self.result_label.setText("⚠ リセットする解析結果がありません。")
                self.result_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_WARNING)};")
        except Exception as ex:
            self.result_label.setText(f"❌ リセット失敗: {ex}")
            self.result_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)};")
