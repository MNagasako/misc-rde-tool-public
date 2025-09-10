# === セッション管理ベースのプロキシ対応 ===
from classes.utils.api_request_helper import api_request

class RDEApiClient:
    """
    RDE APIへのアクセス専用クラス。
    - get, post, put, delete などの基本メソッドを提供
    - DataManager等からcomposeして利用
    """
    def __init__(self, base_url):
        self.base_url = base_url

    def get(self, endpoint, headers=None, params=None):
        url = self.base_url + endpoint
        resp = api_request(url, method='GET', headers=headers, params=params)
        if resp is None:
            raise Exception(f"HTTP request failed for {url}")
        return resp

    # 必要に応じてpost, put, delete等も追加可能
