"""
報告書機能 - HTML解析補助ユーティリティ

BeautifulSoupを使用したHTML解析の補助関数を提供します。

Version: 2.1.0
"""

from typing import Optional
from bs4 import BeautifulSoup, Tag


def safe_extract_text(tag: Optional[Tag], default: str = '') -> str:
    """
    安全にタグからテキストを抽出するヘルパー関数
    
    Args:
        tag: BeautifulSoupのTagオブジェクト（Noneの可能性あり）
        default: タグがNoneまたは次の要素が見つからない場合のデフォルト値
    
    Returns:
        抽出されたテキスト、または default値
    
    Examples:
        >>> tag = soup.find('h5', string='課題番号')
        >>> text = safe_extract_text(tag)  # 次の<p>タグのテキストを取得
    """
    if tag is None:
        return default
    
    next_element = tag.find_next('p')
    if next_element is None:
        return default
    
    return next_element.text.strip()


def safe_find_tag(soup: BeautifulSoup, tag_name: str, string_value: str) -> Optional[Tag]:
    """
    安全にタグを検索するヘルパー関数
    
    Args:
        soup: BeautifulSoupオブジェクト
        tag_name: 検索するタグ名（例: 'h5', 'h2', 'p'）
        string_value: タグ内のテキスト値（完全一致）
    
    Returns:
        見つかったTagオブジェクト、または None
    
    Examples:
        >>> tag = safe_find_tag(soup, 'h5', '課題番号 / Project Issue Number')
        >>> if tag:
        >>>     text = safe_extract_text(tag)
    """
    return soup.find(tag_name, string=string_value)


def extract_text_from_next_p(tag: Optional[Tag], default: str = '') -> str:
    """
    タグの次の<p>要素からテキストを抽出（safe_extract_textのエイリアス）
    
    Args:
        tag: BeautifulSoupのTagオブジェクト
        default: デフォルト値
    
    Returns:
        抽出されたテキスト
    """
    return safe_extract_text(tag, default)


def extract_links_from_next_p(tag: Optional[Tag]) -> list:
    """
    タグの次の<p>要素内の全リンクテキストを抽出
    
    Args:
        tag: BeautifulSoupのTagオブジェクト
    
    Returns:
        リンクテキストのリスト（見つからない場合は空リスト）
    
    Examples:
        >>> tag = soup.find('h2', string='利用した主な設備')
        >>> links = extract_links_from_next_p(tag)
        >>> # ['設備A', '設備B', ...]
    """
    if tag is None:
        return []
    
    next_element = tag.find_next('p')
    if next_element is None:
        return []
    
    link_texts = [a.text.strip() for a in next_element.find_all('a')]
    return link_texts


def extract_list_items(soup: BeautifulSoup, heading_text: str) -> list:
    """
    見出しの後にある<ul>または<ol>内の<li>要素を抽出
    
    プレーンテキストのみを返す（HTMLタグは付与しない）
    
    Args:
        soup: BeautifulSoupオブジェクト
        heading_text: 見出しテキスト
    
    Returns:
        リストアイテムのリスト（プレーンテキスト）
    
    Examples:
        >>> items = extract_list_items(soup, '論文・プロシーディング')
        >>> # ['論文1のタイトルとDOI情報', 'テキストのみの論文2', ...]
    """
    tag = soup.find('h5', string=heading_text)
    if tag is None:
        return []
    
    # ul と ol の両方を探して、最初に見つかった空でないリストを使用
    list_element = None
    
    # まず ol を探す（論文情報は ol を使用する傾向）
    ol_element = tag.find_next('ol')
    if ol_element and ol_element.find('li'):
        list_element = ol_element
    
    # ol が見つからないか空なら ul を探す
    if not list_element:
        ul_element = tag.find_next('ul')
        if ul_element and ul_element.find('li'):
            list_element = ul_element
    
    if list_element is None:
        return []
    
    items = []
    for li in list_element.find_all('li', recursive=False):
        # テキストのみを抽出（HTMLタグは付与しない）
        text = li.get_text(strip=True)
        if text:  # 空でない場合のみ追加
            items.append(text)
    
    return items


def clean_html_text(text: str) -> str:
    """
    HTMLテキストから不要な空白や改行を除去
    
    Args:
        text: クリーニング対象のテキスト
    
    Returns:
        クリーニングされたテキスト
    
    Examples:
        >>> clean_html_text("  text  \\n\\n  ")
        'text'
    """
    if not text:
        return ""
    
    # 前後の空白除去
    text = text.strip()
    
    # 連続する空白を1つに
    import re
    text = re.sub(r'\s+', ' ', text)
    
    return text
