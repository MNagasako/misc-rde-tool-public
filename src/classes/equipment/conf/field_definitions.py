"""
設備データのフィールド定義

ARIM設備情報サイトから取得するフィールドの定義とマッピング情報を提供します。
"""

from typing import List, Dict

# 設備情報サイトから抽出するフィールド一覧
FACILITY_FIELDS: List[str] = [
    "設備ID",
    "分類",
    "設備名称",
    "設置機関",
    "設置場所",
    "メーカー名",
    "型番",
    "キーワード",
    "仕様・特徴"
]

# Excel出力時の列定義（順序も含む）
EXCEL_COLUMNS: List[str] = [
    "code",          # 内部ID
    "設備ID",        # サイト上のID
    "装置名_日",     # 設備名称（日本語）
    "装置名_英",     # 設備名称（英語）
    "PREFIX",        # 設備IDの接頭辞
    "設置機関",      # 所属機関
    "設置場所",      # 設置場所
    "メーカー名",    # 製造元
    "型番",          # モデル番号
    "キーワード",    # 検索用キーワード
    "仕様・特徴",    # 詳細情報
    "分類"           # カテゴリ
]

# フィールド説明（ドキュメント用）
FIELD_DESCRIPTIONS: Dict[str, str] = {
    "code": "内部管理用の連番ID（1から開始）",
    "設備ID": "ARIM設備情報サイトで使用されている設備固有ID",
    "装置名_日": "設備の日本語名称（設備名称から生成）",
    "装置名_英": "設備の英語名称（設備名称から生成、未提供の場合は日本語名）",
    "PREFIX": "設備IDの接頭辞部分（アルファベット部分）",
    "設置機関": "設備が設置されている研究機関名",
    "設置場所": "設備の具体的な設置場所",
    "メーカー名": "設備の製造メーカー名",
    "型番": "設備のモデル番号・型式",
    "キーワード": "検索用のキーワード（複数の場合は改行区切り）",
    "仕様・特徴": "設備の詳細仕様や特徴的な機能",
    "分類": "設備のカテゴリ分類"
}

# デフォルト値（空の場合の代替値）
DEFAULT_VALUES: Dict[str, str] = {
    "code": "",
    "設備ID": "",
    "装置名_日": "",
    "装置名_英": "",
    "PREFIX": "",
    "設置機関": "",
    "設置場所": "",
    "メーカー名": "",
    "型番": "",
    "キーワード": "",
    "仕様・特徴": "",
    "分類": ""
}

def get_field_description(field_name: str) -> str:
    """フィールドの説明を取得
    
    Args:
        field_name: フィールド名
        
    Returns:
        str: フィールドの説明文
    """
    return FIELD_DESCRIPTIONS.get(field_name, "説明なし")

def get_default_value(field_name: str) -> str:
    """フィールドのデフォルト値を取得
    
    Args:
        field_name: フィールド名
        
    Returns:
        str: デフォルト値
    """
    return DEFAULT_VALUES.get(field_name, "")

def validate_field_name(field_name: str) -> bool:
    """フィールド名が有効かチェック
    
    Args:
        field_name: フィールド名
        
    Returns:
        bool: 有効な場合True
    """
    return field_name in EXCEL_COLUMNS or field_name in FACILITY_FIELDS
