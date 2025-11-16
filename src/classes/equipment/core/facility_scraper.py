"""
設備データスクレイパー

ARIM設備情報サイトから設備データを取得する機能を提供します。
"""

import logging
from typing import Optional, Dict
from net.http_helpers import proxy_get
from classes.equipment.util.field_parser import extract_facility_detail, validate_facility_data


logger = logging.getLogger(__name__)


class FacilityScraper:
    """設備データ取得クラス
    
    ARIM設備情報サイトからHTMLを取得し、設備データを抽出します。
    本アプリのhttp_helpersモジュールを使用してネットワーク通信を行います。
    """
    
    def __init__(self, base_url: str = "https://nanonet.go.jp"):
        """初期化
        
        Args:
            base_url: 設備情報サイトのベースURL
        """
        self.base_url = base_url
        self.facility_url = f"{base_url}/facility.php"
        
        logger.info(f"FacilityScraper初期化完了: base_url={base_url}")
    
    def fetch_facility(self, facility_id: int) -> Optional[Dict[str, str]]:
        """設備データを取得
        
        Args:
            facility_id: 設備ID（1から開始）
            
        Returns:
            Optional[Dict[str, str]]: 設備データ辞書。取得失敗時はNone
        """
        url = f"{self.facility_url}?mode=detail&code={facility_id}"
        
        try:
            logger.debug(f"設備データ取得開始: ID={facility_id}, URL={url}")
            
            # http_helpers経由でリクエスト実行（プロキシ・SSL設定自動適用）
            response = proxy_get(url, timeout=60)
            
            if not response:
                logger.warning(f"設備データ取得失敗: ID={facility_id} - レスポンスなし")
                return None
            
            if response.status_code != 200:
                logger.warning(
                    f"設備データ取得失敗: ID={facility_id} - "
                    f"ステータスコード={response.status_code}"
                )
                return None
            
            # 文字コード設定
            response.encoding = 'utf-8'
            html = response.text
            
            # HTMLからデータ抽出
            facility_data = extract_facility_detail(html, facility_id)
            
            # データ検証
            if not validate_facility_data(facility_data):
                logger.debug(f"設備データが空: ID={facility_id}")
                return None
            
            logger.info(
                f"設備データ取得成功: ID={facility_id}, "
                f"設備ID={facility_data.get('設備ID', 'N/A')}"
            )
            
            return facility_data
            
        except Exception as e:
            logger.error(f"設備データ取得エラー: ID={facility_id} - {e}", exc_info=True)
            return None
