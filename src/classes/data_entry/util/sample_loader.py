"""
既存試料データ取得ユーティリティ
"""

import json
import os
from config.common import get_dynamic_file_path

def load_existing_samples(group_id):
    """
    指定されたグループIDの既存試料データを取得
    
    Args:
        group_id: グループID
        
    Returns:
        list: 既存試料データのリスト
    """
    print(f"[SAMPLE_LOADER] 既存試料データ取得開始: group_id={group_id}")
    
    if not group_id:
        print("[SAMPLE_LOADER] グループIDが指定されていません")
        return []
    
    try:
        # サンプルJSONファイルのパスを構築
        sample_file_path = get_dynamic_file_path(f"output/rde/data/samples/{group_id}.json")
        
        if not os.path.exists(sample_file_path):
            print(f"[SAMPLE_LOADER] サンプルファイルが見つかりません: {sample_file_path}")
            return []
        
        print(f"[SAMPLE_LOADER] サンプルファイル読み込み: {sample_file_path}")
        
        with open(sample_file_path, "r", encoding="utf-8") as f:
            sample_data = json.load(f)
        
        # サンプルデータを解析
        samples = []
        data_items = sample_data.get("data", [])
        
        for item in data_items:
            attributes = item.get("attributes", {})
            sample_id = item.get("id", "")
            
            # 試料名を取得（namesから）
            names = attributes.get("names", [])
            sample_name = "未設定"
            if names and len(names) > 0:
                sample_name = names[0]
            
            # 説明を取得
            description = attributes.get("description", "")
            
            # 組成を取得
            composition = attributes.get("composition", "")
            
            sample_info = {
                "id": sample_id,
                "name": sample_name,
                "description": description,
                "composition": composition
            }
            
            samples.append(sample_info)
        
        print(f"[SAMPLE_LOADER] 既存試料データ取得完了: {len(samples)}件")
        
        # デバッグ用に最初の数件を表示
        for i, sample in enumerate(samples[:3]):
            print(f"[SAMPLE_LOADER] サンプル{i+1}: {sample['name'][:30]}...")
        
        return samples
        
    except Exception as e:
        print(f"[SAMPLE_LOADER] 既存試料データ取得エラー: {e}")
        import traceback
        traceback.print_exc()
        return []

def format_sample_display_name(sample_info):
    """
    試料情報を表示用にフォーマット
    
    Args:
        sample_info: 試料情報辞書
        
    Returns:
        str: 表示用文字列
    """
    name = sample_info.get("name", "未設定")
    composition = sample_info.get("composition", "")
    
    if composition:
        return f"{name} ({composition})"
    else:
        return name
