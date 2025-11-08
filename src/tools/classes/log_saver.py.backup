import os
import json
from datetime import datetime
from PyQt5.QtWidgets import QFileDialog, QMessageBox

class LogSaver:
    @staticmethod
    def save_log(parent, request_history, output_log_dir, log_message):
        """リクエスト・レスポンスログをファイルに保存"""
        try:
            filename = QFileDialog.getSaveFileName(
                parent, "ログ保存",
                os.path.join(output_log_dir, f"rde_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"),
                "JSON files (*.json)"
            )[0]
            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(request_history, f, indent=2, ensure_ascii=False)
                QMessageBox.information(parent, "保存完了", f"ログを保存しました: {filename}")
                log_message(f"ログ保存完了: {filename}")
        except Exception as e:
            QMessageBox.critical(parent, "保存エラー", f"ログ保存エラー: {e}")
            log_message(f"ログ保存エラー: {e}")
