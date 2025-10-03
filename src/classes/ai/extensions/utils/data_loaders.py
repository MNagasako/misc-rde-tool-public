"""
AI拡張機能用データローダー
MI.jsonやEQUIPMENTS.jsonの読み込み機能を提供
"""

import os
import json
from typing import Dict, List, Optional, Any
from config.common import get_dynamic_file_path


class MaterialIndexLoader:
    """マテリアルインデックス(MI.json)の読み込み管理"""
    
    _cache: Optional[Dict[str, Any]] = None
    
    @classmethod
    def load_material_index(cls) -> Dict[str, Any]:
        """MI.jsonを読み込み、キャッシュする"""
        if cls._cache is not None:
            return cls._cache
            
        try:
            mi_path = get_dynamic_file_path("input/ai/MI.json")
            if not os.path.exists(mi_path):
                print(f"[WARNING] MI.jsonファイルが見つかりません: {mi_path}")
                return {}
                
            with open(mi_path, 'r', encoding='utf-8') as f:
                cls._cache = json.load(f)
                print(f"[INFO] MI.json読み込み完了: {len(cls._cache)} カテゴリ")
                return cls._cache
                
        except Exception as e:
            print(f"[ERROR] MI.json読み込みエラー: {e}")
            return {}
    
    @classmethod
    def format_for_prompt(cls) -> str:
        """プロンプト用にMI情報をフォーマット"""
        mi_data = cls.load_material_index()
        if not mi_data:
            return "[MI情報未取得]"
            
        try:
            formatted_lines = ["=== マテリアルインデックス（材料分類ツリー）==="]
            
            def format_category(name: str, items: Any, indent: int = 0) -> List[str]:
                lines = []
                prefix = "  " * indent
                
                if isinstance(items, dict):
                    lines.append(f"{prefix}📁 {name}")
                    for sub_name, sub_items in items.items():
                        lines.extend(format_category(sub_name, sub_items, indent + 1))
                elif isinstance(items, list):
                    lines.append(f"{prefix}📁 {name}")
                    for item in items:
                        lines.append(f"{prefix}  • {item}")
                else:
                    lines.append(f"{prefix}• {items}")
                    
                return lines
            
            for category_name, category_data in mi_data.items():
                formatted_lines.extend(format_category(category_name, category_data))
                formatted_lines.append("")  # 空行を追加
                
            formatted_lines.append("=== マテリアルインデックス終了 ===")
            return "\n".join(formatted_lines)
            
        except Exception as e:
            print(f"[ERROR] MI情報フォーマットエラー: {e}")
            return f"[MI情報フォーマットエラー: {e}]"


class EquipmentLoader:
    """装置情報(EQUIPMENTS.json)の読み込み管理"""
    
    _cache: Optional[List[Dict[str, Any]]] = None
    
    @classmethod
    def load_equipment_data(cls) -> List[Dict[str, Any]]:
        """EQUIPMENTS_pretty.jsonを読み込み、キャッシュする"""
        if cls._cache is not None:
            return cls._cache
            
        try:
            # pretty版を優先して使用
            equipment_path = get_dynamic_file_path("input/ai/EQUIPMENTS_pretty.json")
            if not os.path.exists(equipment_path):
                # fallback: 通常版
                equipment_path = get_dynamic_file_path("input/ai/EQUIPMENTS.json")
                
            if not os.path.exists(equipment_path):
                print(f"[WARNING] EQUIPMENTS.jsonファイルが見つかりません: {equipment_path}")
                return []
                
            with open(equipment_path, 'r', encoding='utf-8') as f:
                cls._cache = json.load(f)
                print(f"[INFO] EQUIPMENTS.json読み込み完了: {len(cls._cache)} 装置")
                return cls._cache
                
        except Exception as e:
            print(f"[ERROR] EQUIPMENTS.json読み込みエラー: {e}")
            return []
    
    @classmethod
    def find_equipment_by_ids(cls, equipment_ids: List[str]) -> List[Dict[str, Any]]:
        """設備IDリストに対応する装置情報を取得"""
        if not equipment_ids:
            return []
            
        equipment_data = cls.load_equipment_data()
        found_equipment = []
        
        for equipment in equipment_data:
            equipment_id = equipment.get("設備ID", "")
            if equipment_id in equipment_ids:
                found_equipment.append(equipment)
                
        print(f"[INFO] 装置情報検索: {len(equipment_ids)} ID指定 → {len(found_equipment)} 件発見")
        return found_equipment
    
    @classmethod
    def format_equipment_for_prompt(cls, equipment_list: List[Dict[str, Any]]) -> str:
        """プロンプト用に装置情報をフォーマット"""
        if not equipment_list:
            return "[対応装置情報なし]"
            
        try:
            formatted_lines = ["=== 関連装置情報 ==="]
            formatted_lines.append(f"📊 該当装置数: {len(equipment_list)} 件")
            formatted_lines.append("")
            
            for i, equipment in enumerate(equipment_list, 1):
                formatted_lines.append(f"--- 装置 {i} ---")
                formatted_lines.append(f"設備ID: {equipment.get('設備ID', 'N/A')}")
                formatted_lines.append(f"装置名: {equipment.get('装置名_日', 'N/A')} ({equipment.get('装置名_英', 'N/A')})")
                formatted_lines.append(f"設置機関: {equipment.get('設置機関', 'N/A')}")
                formatted_lines.append(f"設置場所: {equipment.get('設置場所', 'N/A')}")
                formatted_lines.append(f"メーカー: {equipment.get('メーカー名', 'N/A')} - {equipment.get('型番', 'N/A')}")
                
                keywords = equipment.get('キーワード', '')
                if keywords:
                    formatted_lines.append(f"キーワード: {keywords}")
                    
                specs = equipment.get('仕様・特徴', '')
                if specs:
                    formatted_lines.append(f"仕様・特徴: {specs}")
                    
                classification = equipment.get('分類', '')
                if classification:
                    formatted_lines.append(f"分類: {classification}")
                    
                formatted_lines.append("")
                
            formatted_lines.append("=== 関連装置情報終了 ===")
            return "\n".join(formatted_lines)
            
        except Exception as e:
            print(f"[ERROR] 装置情報フォーマットエラー: {e}")
            return f"[装置情報フォーマットエラー: {e}]"