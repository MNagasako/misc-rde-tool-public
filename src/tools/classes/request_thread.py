from PyQt5.QtCore import Qt, QThread, pyqtSignal
from typing import Dict, Optional

class RequestThread(QThread):
    """非同期HTTPリクエスト実行用スレッド"""
    request_completed = pyqtSignal(dict)

    def __init__(self, analyzer, method: str, url: str,
                 headers: Optional[Dict], data: Optional[Dict],
                 params: Optional[Dict], json_data: Optional[Dict]):
        super().__init__()
        self.analyzer = analyzer
        self.method = method
        self.url = url
        self.headers = headers
        self.data = data
        self.params = params
        self.json_data = json_data

    def run(self):
        result = self.analyzer.make_request(
            method=self.method,
            url=self.url,
            headers=self.headers,
            data=self.data,
            params=self.params,
            json_data=self.json_data
        )
        self.request_completed.emit(result)
