"""
報告書機能 - スクレイピングエンジン

報告書サイトからデータを取得し、HTML解析を行います。

Version: 2.1.0
"""

import re
import math
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs, urlencode
from bs4 import BeautifulSoup

# HTTPヘルパー（本アプリの統一されたrequests機能）
from net.http_helpers import proxy_get, proxy_post

# 報告書機能の設定とユーティリティ
from ..conf.field_definitions import (
    EXCEL_COLUMNS,
    BASE_URL,
    REPORT_LIST_URL,
    REPORT_DETAIL_URL,
    PAGINATION_SELECTOR,
    REPORT_LIST_DEFAULT_QUERY,
    REPORTS_PER_PAGE,
)
from ..util.html_parser import (
    safe_extract_text,
    safe_find_tag,
    extract_links_from_next_p,
    extract_list_items,
    clean_html_text,
)


@dataclass
class ReportListingSummary:
    """報告書一覧のサマリ情報"""

    total_count: int
    final_page: int


class ReportScraper:
    """
    報告書スクレイピングエンジン
    
    報告書サイトへのアクセス、HTML解析、データ抽出を担当します。
    """
    
    def __init__(self):
        """初期化"""
        self.logger = logging.getLogger(__name__)
        self.base_url = BASE_URL
        self.list_url = REPORT_LIST_URL
        self.detail_url_template = REPORT_DETAIL_URL
        self.list_query = REPORT_LIST_DEFAULT_QUERY.copy()
        self.per_page = REPORTS_PER_PAGE
    
    def get_report_list(
        self,
        max_pages: Optional[int] = None,
        start_page: int = 1
    ) -> List[Dict[str, str]]:
        """
        報告書一覧を取得
        
        Args:
            max_pages: 取得する最大ページ数（Noneの場合は全ページ）
            start_page: 開始ページ番号
        
        Returns:
            報告書リンク情報のリスト
            [{"code": "...", "key": "...", "url": "...", "title": "..."}, ...]
        
        Raises:
            Exception: HTTPエラーやパースエラー
        """
        self.logger.info(f"報告書一覧取得開始: start_page={start_page}, max_pages={max_pages}")
        
        summary = self._get_listing_summary()
        if summary:
            final_page = summary.final_page
            total_count = summary.total_count
        else:
            final_page = 1
            total_count = 0
            self.logger.warning("一覧サマリの取得に失敗したため、1ページのみ処理します")

        # max_pagesが指定されている場合は制限
        if max_pages:
            end_page = min(start_page + max_pages - 1, final_page)
        else:
            end_page = final_page

        if total_count:
            self.logger.info(
                f"総件数 {total_count} 件 / ページ範囲: {start_page} - {end_page} (最終: {final_page})"
            )
        else:
            self.logger.info(
                f"ページ範囲: {start_page} - {end_page} (最終: {final_page})"
            )
        
        # 各ページから報告書リンクを取得
        all_links = []
        for page_num in range(start_page, end_page + 1):
            try:
                links = self._get_links_from_page(page_num)
                all_links.extend(links)
                self.logger.info(f"ページ {page_num}: {len(links)} 件取得")
            except Exception as e:
                self.logger.error(f"ページ {page_num} の取得失敗: {e}")
                continue
        
        self.logger.info(f"報告書一覧取得完了: 合計 {len(all_links)} 件")
        return all_links

    def get_listing_summary(self) -> Optional[ReportListingSummary]:
        """外部向けの一覧サマリAPI"""
        return self._get_listing_summary()
    
    def search_reports_by_keyword(self, keyword: str) -> List[Dict[str, str]]:
        """
        キーワードで報告書を検索（POST検索）
        
        Args:
            keyword: 検索キーワード（課題番号など）
        
        Returns:
            報告書リンク情報のリスト
            [{"code": "...", "key": "...", "url": "...", "title": "..."}, ...]
        
        Note:
            報告書サイトのPOST検索機能を使用します。
            URL: https://nanonet.go.jp/user_report.php
            Method: POST
            Content-Type: application/x-www-form-urlencoded
            Body: keyword=<検索キーワード>
        """
        self.logger.info(f"報告書キーワード検索開始: keyword={keyword}")
        
        try:
            # POST検索実行
            form_data = {'keyword': keyword}
            response = proxy_post(
                self.list_url,
                data=form_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                self.logger.warning(f"検索失敗: HTTPステータス {response.status_code}")
                return []
            
            # レスポンスHTMLをパース
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 報告書リンクを抽出（_get_links_from_page と同じロジック）
            links = []
            
            for a_tag in soup.find_all('a', href=True):
                href = a_tag.get('href', '')
                
                # hrefを文字列に変換
                if not isinstance(href, str):
                    continue
                
                # 報告書詳細ページのリンクをフィルタ
                if 'user_report.php' in href and 'mode=detail' in href and 'code=' in href and 'key=' in href:
                    # 絶対URLに変換
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            full_url = f"{self.base_url}{href}"
                        else:
                            full_url = f"{self.base_url}/{href}"
                    else:
                        full_url = href
                    
                    # URLからcode/keyを抽出
                    try:
                        parsed_url = urlparse(full_url)
                        params = parse_qs(parsed_url.query)
                        code = params.get('code', [None])[0]
                        key = params.get('key', [None])[0]
                        
                        if code and key:
                            # タイトルを取得
                            title = a_tag.get_text(strip=True) or f"Report {code}"
                            
                            link_info = {
                                'code': code,
                                'key': key,
                                'url': full_url,
                                'title': title
                            }
                            
                            # 重複チェック
                            if not any(l['code'] == code and l['key'] == key for l in links):
                                links.append(link_info)
                    
                    except Exception as e:
                        self.logger.warning(f"リンク解析エラー ({href}): {e}")
                        continue
            
            self.logger.info(f"キーワード検索完了: {len(links)} 件の報告書を発見")
            return links
            
        except Exception as e:
            self.logger.error(f"キーワード検索エラー: {e}")
            return []
    
    def fetch_report(self, report_url: str) -> Optional[Dict]:
        """
        単一報告書の詳細を取得
        
        Args:
            report_url: 報告書の詳細ページURL
        
        Returns:
            報告書データ（辞書形式）、エラー時はNone
        
        Examples:
            >>> scraper = ReportScraper()
            >>> data = scraper.fetch_report("https://nanonet.go.jp/report.php?mode=detail&code=XXX&key=YYY")
            >>> print(data['課題番号 / Project Issue Number'])
        """
        self.logger.info(f"報告書取得: {report_url}")
        
        try:
            # URLからcode/keyを抽出
            parsed_url = urlparse(report_url)
            params = parse_qs(parsed_url.query)
            code = params.get('code', [None])[0]
            key = params.get('key', [None])[0]
            
            # HTMLを取得（http_helpers経由）
            response = proxy_get(report_url)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                self.logger.warning(f"HTTPエラー: {response.status_code}")
                return None
            
            # HTMLからフィールドを抽出
            report_data = self.extract_report_fields(response.text)
            
            # code/keyを追加
            report_data['code'] = code if code else ''
            report_data['key'] = key if key else ''
            
            self.logger.info(f"報告書取得成功: code={code}")
            return report_data
            
        except Exception as e:
            self.logger.error(f"報告書取得エラー ({report_url}): {e}", exc_info=True)
            return None
    
    def extract_report_fields(self, html_content: str) -> Dict:
        """
        HTMLから報告書フィールドを抽出
        
        Args:
            html_content: 報告書ページのHTML
        
        Returns:
            抽出されたフィールドデータ（辞書形式）
        
        Note:
            EXCEL_COLUMNSに定義された全フィールドを抽出します。
            見つからないフィールドは空文字列になります。
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        extracted_data = {}
        
        # 基本フィールドの抽出
        basic_fields = [
            "課題番号 / Project Issue Number",
            "利用課題名 / Title",
            "利用した実施機関 / Support Institute",
            "機関外・機関内の利用 / External or Internal Use",
        ]
        
        for field_name in basic_fields:
            tag = safe_find_tag(soup, 'h5', field_name)
            extracted_data[field_name] = safe_extract_text(tag)
        
        # 技術領域の抽出（横断技術領域・重要技術領域）
        self._extract_technology_areas(soup, extracted_data)
        
        # キーワードの抽出
        extracted_data['キーワード / Keywords'] = self._extract_keywords(soup, html_content)
        
        # 利用者情報の抽出
        user_fields = [
            "利用者名（課題申請者）/ User Name (Project Applicant)",
            "所属名 / Affiliation",
        ]
        
        for field_name in user_fields:
            tag = safe_find_tag(soup, 'h5', field_name)
            extracted_data[field_name] = safe_extract_text(tag)
        
        # 共同利用者（特殊処理が必要）
        self._extract_collaborators(soup, extracted_data)
        
        # ARIM支援担当者
        field_name = "ARIM実施機関支援担当者 / Names of Collaborators in The Hub and Spoke Institutes"
        tag = safe_find_tag(soup, 'h5', field_name)
        extracted_data[field_name] = safe_extract_text(tag)
        
        # 利用形態の抽出
        self._extract_support_types(soup, extracted_data)
        
        # 利用した主な設備（リンクリスト）
        field_name = "利用した主な設備 / Equipment Used in This Project"
        tag = safe_find_tag(soup, 'h2', field_name)
        equipment_links = extract_links_from_next_p(tag)
        extracted_data[field_name] = equipment_links if equipment_links else []
        
        # 大きなテキストフィールド
        large_text_fields = [
            "概要（目的・用途・実施内容）/ Abstract (Aim, Use Applications and Contents)",
            "実験 / Experimental",
            "結果と考察 / Results and Discussion",
            "その他・特記事項（参考文献・謝辞等） / Remarks(References and Acknowledgements)",
        ]
        
        for field_name in large_text_fields:
            tag = safe_find_tag(soup, 'h5', field_name)
            extracted_data[field_name] = safe_extract_text(tag)
        
        # 論文・発表のリスト
        extracted_data['論文・プロシーディング（DOIのあるもの） / DOI (Publication and Proceedings)'] = \
            extract_list_items(soup, '論文・プロシーディング（DOIのあるもの） / DOI (Publication and Proceedings)')
        
        extracted_data['口頭発表、ポスター発表および、その他の論文 / Oral Presentations etc.'] = \
            extract_list_items(soup, '口頭発表、ポスター発表および、その他の論文 / Oral Presentations etc.')
        
        # 特許件数
        self._extract_patent_counts(soup, extracted_data)
        
        return extracted_data
    
    # ========================================
    # プライベートメソッド
    # ========================================
    
    def _get_listing_summary(self) -> Optional[ReportListingSummary]:
        """報告書一覧ページのサマリ情報を取得"""
        try:
            self.logger.info("一覧サマリ取得中...")
            response = proxy_get(self._build_list_url())
            if response.status_code != 200:
                self.logger.warning(
                    f"一覧サマリ取得失敗: ステータス{response.status_code}"
                )
                return None

            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')

            total_count = self._extract_total_count(soup)
            final_page = self._extract_final_page(soup)

            if total_count is None and final_page is None:
                self.logger.warning("総件数・最終ページの特定に失敗しました")
                return None

            if total_count is None and final_page is not None:
                total_count = final_page * self.per_page
            if final_page is None and total_count is not None:
                final_page = max(1, math.ceil(total_count / self.per_page))

            summary = ReportListingSummary(
                total_count=total_count or 0,
                final_page=final_page or 1
            )
            self.logger.info(
                f"一覧サマリ: 総件数={summary.total_count}, 最終ページ={summary.final_page}"
            )
            return summary

        except Exception as e:
            self.logger.error(f"一覧サマリ取得エラー: {e}")
            return None

    def _extract_total_count(self, soup: BeautifulSoup) -> Optional[int]:
        dt_tag = soup.select_one('.pageNavBox dt')
        if not dt_tag:
            return None
        text = dt_tag.get_text(strip=True)
        match = re.search(r"(\d+)件中", text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def _extract_final_page(self, soup: BeautifulSoup) -> Optional[int]:
        page_links = soup.select(PAGINATION_SELECTOR)
        if not page_links:
            return None

        max_page = 0
        for link in page_links:
            href_value = link.get('href', '')
            href = str(href_value) if href_value is not None else ''
            if 'page=' not in href:
                continue
            try:
                page_value = int(href.split('page=')[1].split('&')[0])
                max_page = max(max_page, page_value)
            except (ValueError, IndexError):
                continue

        return max_page or None

    def _build_list_url(self, page: Optional[int] = None) -> str:
        params = self.list_query.copy()
        if page is not None:
            params['page'] = str(page)
        query = urlencode(params)
        return f"{self.list_url}?{query}"
    
    def _get_links_from_page(self, page_num: int) -> List[Dict[str, str]]:
        """
        指定ページから報告書リンクを取得
        
        Args:
            page_num: ページ番号
        
        Returns:
            報告書リンク情報のリスト
            [{"code": "...", "key": "...", "url": "...", "title": "..."}, ...]
        """
        url = self._build_list_url(page_num)
        
        try:
            response = proxy_get(url)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                raise Exception(f"HTTPエラー: {response.status_code}")
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 報告書リンクを抽出
            # 報告書一覧は通常<a>タグで、href="report.php?mode=detail&code=XXX&key=YYY"の形式
            links = []
            
            # 詳細ページへのリンクを全て取得
            for a_tag in soup.find_all('a', href=True):
                href = a_tag.get('href', '')
                
                # hrefを文字列に変換
                if not isinstance(href, str):
                    continue
                
                # 報告書詳細ページのリンクをフィルタ（user_report.php に修正）
                if 'user_report.php' in href and 'mode=detail' in href and 'code=' in href and 'key=' in href:
                    # 絶対URLに変換
                    if not href.startswith('http'):
                        if href.startswith('/'):
                            full_url = f"{self.base_url}{href}"
                        else:
                            full_url = f"{self.base_url}/{href}"
                    else:
                        full_url = href
                    
                    # URLからcode/keyを抽出
                    try:
                        parsed_url = urlparse(full_url)
                        params = parse_qs(parsed_url.query)
                        code = params.get('code', [None])[0]
                        key = params.get('key', [None])[0]
                        
                        if code and key:
                            # タイトルを取得（リンクテキストまたは近隣要素）
                            title = a_tag.get_text(strip=True) or f"Report {code}"
                            
                            link_info = {
                                'code': code,
                                'key': key,
                                'url': full_url,
                                'title': title
                            }
                            
                            # 重複チェック
                            if not any(l['code'] == code and l['key'] == key for l in links):
                                links.append(link_info)
                    
                    except Exception as e:
                        self.logger.warning(f"リンク解析エラー ({href}): {e}")
                        continue
            
            self.logger.debug(f"ページ {page_num}: {len(links)} 件のリンクを抽出")
            return links
            
        except Exception as e:
            self.logger.error(f"ページ {page_num} 取得エラー: {e}")
            raise
    
    def _extract_technology_areas(self, soup: BeautifulSoup, data: Dict) -> None:
        """技術領域（横断・重要）を抽出"""
        tag_name = '技術領域 / Technology Area'
        tag = safe_find_tag(soup, 'h5', tag_name)
        
        if tag is not None:
            # 横断技術領域の処理
            cross_tech_element = tag.find_next('p')
            if cross_tech_element is not None:
                cross_tech_text = cross_tech_element.text.strip()
                main, sub = self._parse_main_sub_fields(cross_tech_text)
                data["横断技術領域・主"] = main
                data["横断技術領域・副"] = sub
            else:
                data["横断技術領域・主"] = ""
                data["横断技術領域・副"] = ""
            
            # 重要技術領域の処理（横断技術領域の次の<p>）
            if cross_tech_element is not None:
                important_tech_element = cross_tech_element.find_next('p')
                if important_tech_element is not None:
                    important_tech_text = important_tech_element.text.strip()
                    main, sub = self._parse_main_sub_fields(important_tech_text)
                    data["重要技術領域・主"] = main
                    data["重要技術領域・副"] = sub
                else:
                    data["重要技術領域・主"] = ""
                    data["重要技術領域・副"] = ""
        else:
            data["横断技術領域・主"] = ""
            data["横断技術領域・副"] = ""
            data["重要技術領域・主"] = ""
            data["重要技術領域・副"] = ""
    
    def _parse_main_sub_fields(self, text: str) -> tuple[str, str]:
        """
        主・副フィールドをパース
        
        形式: 【XXX】（主 / Main）<主の値>（副 / Sub）<副の値>
        
        Args:
            text: パース対象のテキスト
        
        Returns:
            (主の値, 副の値) のタプル
        """
        main = ""
        sub = ""
        
        # 主の抽出: "主" を含む括弧の後、次の括弧または行末まで
        main_match = re.search(r'[（(][^）)]*主[^）)]*[）)]\s*([^（(]+?)(?=[（(]|$)', text)
        if main_match:
            main = main_match.group(1).strip()
            # 末尾の「/」以降（英語部分）を削除
            if '/' in main:
                main = main.split('/')[0].strip()
        
        # 副の抽出: "副" を含む括弧の後、行末まで
        sub_match = re.search(r'[（(][^）)]*副[^）)]*[）)]\s*(.+?)$', text)
        if sub_match:
            sub = sub_match.group(1).strip()
            # 末尾の「/」以降（英語部分）を削除
            if '/' in sub:
                sub = sub.split('/')[0].strip()
            # 「-」は未設定を意味する
            if sub == '-':
                sub = ""
        
        return main, sub
    
    def _extract_keywords(self, soup: BeautifulSoup, html_content: str) -> str:
        """キーワードを抽出"""
        field_name = 'キーワード / Keywords'
        tag = safe_find_tag(soup, 'h5', field_name)
        return safe_extract_text(tag)
    
    def _extract_collaborators(self, soup: BeautifulSoup, data: Dict) -> None:
        """共同利用者を抽出"""
        field_name = '共同利用者氏名 / Names of Collaborators in Other Institutes Than Hub and Spoke Institutes'
        tag = soup.find('h5', string=field_name)
        
        if tag is None:
            data[field_name] = ''
        else:
            next_element = tag.find_next()
            if next_element and next_element.name == 'p':
                data[field_name] = next_element.text.strip()
            else:
                data[field_name] = ''
    
    def _extract_support_types(self, soup: BeautifulSoup, data: Dict) -> None:
        """利用形態を抽出"""
        field_name = '利用形態 / Support Type'
        tag = safe_find_tag(soup, 'h5', field_name)
        
        if tag is not None:
            support_element = tag.find_next('p')
            if support_element is not None:
                support_text = support_element.text.strip()
                # 「主: XXX、副: YYY」のようなパターンを解析
                main_match = re.search(r'主[:：]\s*([^、]+)', support_text)
                sub_match = re.search(r'副[:：]\s*(.+)', support_text)
                
                data["利用形態・主"] = main_match.group(1).strip() if main_match else ""
                data["利用形態・副"] = sub_match.group(1).strip() if sub_match else ""
            else:
                data["利用形態・主"] = ""
                data["利用形態・副"] = ""
        else:
            data["利用形態・主"] = ""
            data["利用形態・副"] = ""
    
    def _extract_patent_counts(self, soup: BeautifulSoup, data: Dict) -> None:
        """特許件数を抽出"""
        # 特許出願件数
        tag = safe_find_tag(soup, 'h5', '特許出願件数')
        data['特許出願件数'] = safe_extract_text(tag, default='0')
        
        # 特許登録件数
        tag = safe_find_tag(soup, 'h5', '特許登録件数')
        data['特許登録件数'] = safe_extract_text(tag, default='0')
