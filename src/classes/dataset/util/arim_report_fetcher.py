"""
ARIM利用報告書取得モジュール
ARIM利用報告書サイトから課題番号に基づいて報告書データを取得する
"""

import re
from net.http_helpers import proxy_get, proxy_post
from bs4 import BeautifulSoup
from config.common import get_base_dir


class ARIMReportFetcher:
    """ARIM利用報告書取得クラス"""
    
    BASE_URL = "https://nanonet.go.jp/user_report.php"
    
    def __init__(self):
        # User-Agentヘッダーを定義（リクエストごとに使用）
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def extract_project_number(self, grant_number):
        """課題番号から検索用の番号を抽出"""
        try:
            # JPMXP12**23TU0177** の形式から 23TU0177 を抽出
            pattern = r'JPMXP\d+(.+)'
            match = re.search(pattern, grant_number)
            if match:
                return match.group(1)
            else:
                # プリフィックスがない場合はそのまま返す
                return grant_number
        except Exception as e:
            print(f"[WARNING] 課題番号抽出エラー: {e}")
            return grant_number
    
    def search_report(self, project_number):
        """報告書を検索してリストを取得"""
        try:
            # 検索リクエスト
            search_data = {
                'keyword': project_number
            }
            
            print(f"[DEBUG] ARIM報告書検索: {project_number}")
            
            response = proxy_post(self.BASE_URL, data=search_data, headers=self.headers)
            response.raise_for_status()
            
            # HTMLをパース
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 検索結果を解析
            report_list = soup.find('div', class_='reportList')
            if not report_list:
                print(f"[INFO] 報告書が見つかりませんでした: {project_number}")
                return None
            
            # 詳細リンクを抽出
            links = report_list.find_all('a', href=True)
            detail_link = None
            
            for link in links:
                if 'mode=detail' in link['href']:
                    detail_link = link['href']
                    break
            
            if not detail_link:
                print(f"[WARNING] 詳細リンクが見つかりませんでした: {project_number}")
                return None
            
            # 完全URLに変換
            if detail_link.startswith('user_report.php'):
                detail_url = f"https://nanonet.go.jp/{detail_link}"
            else:
                detail_url = detail_link
            
            print(f"[DEBUG] 詳細URL: {detail_url}")
            return detail_url
            
        except Exception as e:
            print(f"[ERROR] ARIM報告書検索エラー: {e}")
            return None
    
    def fetch_report_detail(self, detail_url):
        """報告書詳細データを取得"""
        try:
            print(f"[DEBUG] 報告書詳細取得: {detail_url}")
            
            response = proxy_get(detail_url, timeout=30, headers=self.headers)
            response.raise_for_status()
            
            # HTMLをパース
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 報告書データを抽出
            report_data = self.parse_report_content(soup)
            
            print(f"[DEBUG] 報告書データ取得完了: {len(report_data)}項目")
            
            # デバッグ: 取得したデータの概要を表示
            for key, value in report_data.items():
                preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                print(f"[DEBUG] {key}: {preview}")
            
            return report_data
            
        except Exception as e:
            # HTTP通信エラーも含めて一般的な例外処理で対応
            if "ConnectionError" in str(type(e)) or "timeout" in str(e).lower() or "http" in str(e).lower():
                print(f"[ERROR] HTTP通信エラー: {e}")
            else:
                print(f"[ERROR] 報告書詳細取得エラー: {e}")
            return {}
    
    def parse_report_content(self, soup):
        """HTMLから報告書内容を解析"""
        report_data = {}
        
        try:
            # contentsセクションを取得
            contents = soup.find('article', id='contents')
            if not contents:
                contents = soup.find('div', id='contents')
            
            if not contents:
                print("[WARNING] コンテンツセクションが見つかりません")
                return report_data
            
            # h5タグとその次のpタグの組み合わせでデータを抽出
            h5_tags = contents.find_all('h5')
            
            for h5 in h5_tags:
                try:
                    header_text = h5.get_text(strip=True)
                    
                    # 次のpタグまたはolタグを取得
                    next_element = h5.find_next_sibling(['p', 'ol'])
                    if next_element:
                        value_text = next_element.get_text(strip=True)
                        
                        # データマッピング
                        key = self.map_header_to_key(header_text)
                        if key:
                            # 特別な処理: キーワードの場合は改行やHTMLタグを処理
                            if key == 'arim_report_keywords':
                                # キーワードの後に続く余分なテキストを除去
                                if '利用者と利用形態' in value_text:
                                    value_text = value_text.split('利用者と利用形態')[0].strip()
                                if value_text.endswith('</p>'):
                                    value_text = value_text.replace('</p>', '').strip()
                            
                            report_data[key] = value_text
                            print(f"[DEBUG] データ抽出: {key} = {value_text[:50]}...")
                    
                except Exception as e:
                    print(f"[WARNING] 要素解析エラー: {e}")
                    continue
            
            # wysiwygクラスの特別処理
            wysiwyg_elements = contents.find_all(class_='user_report_wysiwyg')
            for element in wysiwyg_elements:
                try:
                    # 前のh5を探す
                    prev_h5 = element.find_previous('h5')
                    if prev_h5:
                        header_text = prev_h5.get_text(strip=True)
                        key = self.map_header_to_key(header_text)
                        if key:
                            value_text = element.get_text(strip=True)
                            report_data[key] = value_text
                            print(f"[DEBUG] WYSIWYG データ抽出: {key} = {value_text[:50]}...")
                except Exception as e:
                    print(f"[WARNING] WYSIWYG要素解析エラー: {e}")
                    continue
            
            return report_data
            
        except Exception as e:
            print(f"[ERROR] 報告書コンテンツ解析エラー: {e}")
            return {}
    
    def map_header_to_key(self, header_text):
        """ヘッダーテキストをプレースホルダキーにマッピング"""
        mappings = {
            # 基本情報
            '課題番号': 'arim_report_project_number',
            '利用課題名': 'arim_report_title',
            '利用した実施機関': 'arim_report_institute',
            '機関外・機関内の利用': 'arim_report_usage_type',
            'ARIM半導体基盤PF関連課題': 'arim_report_semiconductor',
            '技術領域': 'arim_report_tech_area',
            'キーワード': 'arim_report_keywords',
            
            # 利用者情報
            '利用者名（課題申請者）': 'arim_report_user_name',
            '所属名': 'arim_report_affiliation',
            '共同利用者氏名': 'arim_report_collaborators',
            'ARIM実施機関支援担当者': 'arim_report_supporters',
            '利用形態': 'arim_report_support_type',
            
            # 報告書内容
            '概要（目的・用途・実施内容）': 'arim_report_abstract',
            '実験': 'arim_report_experimental',
            '結果と考察': 'arim_report_results',
            'その他・特記事項（参考文献・謝辞等）': 'arim_report_remarks',
            
            # 成果
            '論文・プロシーディング（DOIのあるもの）': 'arim_report_publications',
            '口頭発表、ポスター発表および、その他の論文': 'arim_report_presentations',
            '特許': 'arim_report_patents'
        }
        
        # 部分一致で検索
        for header_key, placeholder_key in mappings.items():
            if header_key in header_text:
                return placeholder_key
        
        return None
    
    def fetch_report_by_grant_number(self, grant_number):
        """課題番号から報告書データを取得"""
        try:
            # 課題番号から検索用番号を抽出
            project_number = self.extract_project_number(grant_number)
            
            # 報告書を検索
            detail_url = self.search_report(project_number)
            if not detail_url:
                return {}
            
            # 詳細データを取得
            report_data = self.fetch_report_detail(detail_url)
            
            return report_data
            
        except Exception as e:
            print(f"[ERROR] ARIM報告書取得エラー: {e}")
            return {}


def get_arim_report_fetcher():
    """ARIMReportFetcherのインスタンスを取得"""
    return ARIMReportFetcher()


def fetch_arim_report_data(grant_number):
    """課題番号からARIM報告書データを取得するヘルパー関数"""
    try:
        fetcher = get_arim_report_fetcher()
        return fetcher.fetch_report_by_grant_number(grant_number)
    except Exception as e:
        print(f"[ERROR] ARIM報告書データ取得エラー: {e}")
        return {}