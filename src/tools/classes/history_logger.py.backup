import json
from typing import Dict, List

class HistoryLogger:
    """リクエスト履歴・ログ管理ユーティリティクラス"""

    @staticmethod
    def add_to_history(request_history: List[Dict], history_table, result: Dict):
        """履歴テーブルに追加"""
        request_history.append(result)
        row = history_table.rowCount()
        history_table.insertRow(row)
        # 時刻
        timestamp = result.get('timestamp', 'Unknown')
        history_table.setItem(row, 0, HistoryLogger._make_item(timestamp))
        # メソッド
        method = result.get('request', {}).get('method', 'Unknown')
        history_table.setItem(row, 1, HistoryLogger._make_item(method))
        # URL
        url = result.get('request', {}).get('url', 'Unknown')
        history_table.setItem(row, 2, HistoryLogger._make_item(url))
        # ステータス
        if 'response' in result:
            status = str(result['response'].get('status_code', 'Unknown'))
        else:
            status = 'Error'
        history_table.setItem(row, 3, HistoryLogger._make_item(status))
        # レスポンス時間（未実装）
        history_table.setItem(row, 4, HistoryLogger._make_item("N/A"))

    @staticmethod
    def display_request_result(log_display, result: Dict):
        """リクエスト結果表示（ログエリア用）"""
        timestamp = result.get('timestamp', 'Unknown')
        log_text = f"\n=== リクエスト結果 ({timestamp}) ===\n"
        request_info = result.get('request', {})
        log_text += f"メソッド: {request_info.get('method', 'Unknown')}\n"
        log_text += f"URL: {request_info.get('url', 'Unknown')}\n"
        if 'response' in result:
            response_info = result['response']
            log_text += f"ステータスコード: {response_info.get('status_code', 'Unknown')}\n"
            log_text += f"レスポンスURL: {response_info.get('url', 'Unknown')}\n"
            headers = response_info.get('headers', {})
            log_text += f"レスポンスヘッダー: {json.dumps(headers, indent=2, ensure_ascii=False)}\n"
            body = response_info.get('body', '')
            if isinstance(body, dict):
                log_text += f"レスポンスボディ: {json.dumps(body, indent=2, ensure_ascii=False)}\n"
            else:
                if len(str(body)) > 500:
                    log_text += f"レスポンスボディ: {str(body)[:500]}... (truncated)\n"
                else:
                    log_text += f"レスポンスボディ: {body}\n"
        if 'error' in result:
            log_text += f"エラー: {result['error']}\n"
        log_text += "=" * 50 + "\n"
        log_display.append(log_text)
        # 最下部にスクロール
        cursor = log_display.textCursor()
        cursor.movePosition(cursor.End)
        log_display.setTextCursor(cursor)

    @staticmethod
    def clear_log(log_display, request_history: List[Dict], history_table):
        log_display.clear()
        request_history.clear()
        history_table.setRowCount(0)

    @staticmethod
    def _make_item(text):
        from PyQt5.QtWidgets import QTableWidgetItem
        return QTableWidgetItem(text)
