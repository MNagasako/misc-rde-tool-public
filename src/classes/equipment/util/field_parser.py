"""設備データHTML解析ユーティリティ

ARIM設備情報サイトのHTMLからデータを抽出・整形する機能を提供します。
"""

import html as html_lib
import re
from typing import Dict, Optional
from classes.equipment.conf.field_definitions import FACILITY_FIELDS
from classes.equipment.util.name_parser import split_device_name_from_facility_name


def extract_facility_detail(html: str, facility_id: int) -> Dict[str, str]:
    """設備詳細情報をHTMLから抽出
    
    Args:
        html: 設備詳細ページのHTML
        facility_id: 設備ID（内部管理用）
        
    Returns:
        Dict[str, str]: 抽出された設備情報
    """
    result = {"code": str(facility_id)}
    
    # <div id="facilityDetail"> セクションを抽出
    facility_detail_match = re.findall(
        r'<div id="facilityDetail">.*?</div>', 
        html, 
        flags=re.DOTALL
    )
    
    if not facility_detail_match:
        return result
    
    # 各フィールドを抽出
    for field_name in FACILITY_FIELDS:
        value = extract_field_value(html, field_name)
        result[field_name] = value
    
    # 追加フィールドの生成
    if "設備名称" in result:
        ja, en = split_device_name_from_facility_name(result.get("設備名称") or "")
        result["装置名_日"] = ja
        result["装置名_英"] = en
    
    # PREFIX（設備IDの接頭辞）を抽出
    if "設備ID" in result and result["設備ID"]:
        prefix_match = re.search(r'^[A-Za-z]*', result["設備ID"])
        result["PREFIX"] = prefix_match.group(0) if prefix_match else ""
    else:
        result["PREFIX"] = ""
    
    return result


def extract_field_value(html: str, field_name: str) -> str:
    """HTMLから特定フィールドの値を抽出
    
    Args:
        html: HTML文字列
        field_name: フィールド名
        
    Returns:
        str: 抽出された値（見つからない場合は空文字列）
    """
    # <th>フィールド名</th>...<td>値</td> のパターンを検索
    pattern = r'<th scope="row">{}</th>.*?</td>'.format(re.escape(field_name))
    matches = re.findall(pattern, html, flags=re.DOTALL)
    
    if not matches:
        return ""
    
    # 最初のマッチから値を抽出
    value = matches[0]
    
    # HTMLをクリーニング
    value = clean_html_value(value, field_name)
    
    return value


def clean_html_value(value: str, field_name: str = "") -> str:
    """HTML値をクリーニング
    
    Args:
        value: クリーニング対象の文字列
        field_name: フィールド名（オプション）
        
    Returns:
        str: クリーニングされた文字列
    """
    # タブと nbsp を削除（その他の実体参照は後段でunescape）
    value = re.sub(r'\t|&nbsp;', '', value, flags=re.DOTALL)
    
    # <th>タグと<td>タグを削除
    if field_name:
        value = re.sub(
            r'<th scope="row">{}</th>|\r\n|\n|<td>|</td>'.format(re.escape(field_name)),
            '',
            value,
            flags=re.DOTALL
        )
    else:
        value = re.sub(r'<td>|</td>|\r\n', '', value, flags=re.DOTALL)
    
    # <br>タグを改行に変換
    value = re.sub(r'<br>|<br />', '\n', value, flags=re.DOTALL)

    # HTML実体参照をデコード（&ensp; 等）
    try:
        value = html_lib.unescape(value)
    except Exception:
        pass
    
    # 先頭・末尾の空白を削除
    value = value.strip()
    
    return value


def validate_facility_data(data: Dict[str, str]) -> bool:
    """設備データの妥当性をチェック
    
    Args:
        data: 設備データ辞書
        
    Returns:
        bool: 有効なデータの場合True
    """
    # 最低限、設備IDが存在することを確認
    return bool(data.get("設備ID"))


def extract_prefix_from_id(facility_id_str: str) -> str:
    """設備IDから接頭辞を抽出
    
    Args:
        facility_id_str: 設備ID文字列
        
    Returns:
        str: 接頭辞（アルファベット部分）
    """
    if not facility_id_str:
        return ""
    
    match = re.search(r'^[A-Za-z]*', facility_id_str)
    return match.group(0) if match else ""
