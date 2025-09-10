#!/usr/bin/env python3
"""
重複メソッド段階的削除スクリプト
自動生成 - 2025年8月24日
"""
import os
import re
from pathlib import Path

def remove_method_from_file(file_path, method_name):
    """ファイルから指定メソッドを安全削除"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # メソッド定義の検索パターン
    pattern = rf'\n\s*def {method_name}\(.*?\):(.*?)(?=\n\s*def |\n\s*class |\Z)'
    
    matches = list(re.finditer(pattern, content, re.DOTALL))
    
    if matches:
        # 最初のマッチを削除
        match = matches[0]
        new_content = content[:match.start()] + content[match.end():]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return True, len(matches)
    
    return False, 0

def execute_phase_1():
    """Phase 1: AI機能完全重複削除"""
    print("🔧 Phase 1: AI機能重複削除開始")
    
    target_file = Path('src/classes/ui_ai_test.py')
    methods_to_delete = [
        'test_ai_connection',
        'send_ai_prompt',
        '_validate_task_and_experiment_selection',
        '_execute_analysis_single', 
        '_execute_analysis_batch'
    ]
    
    total_removed = 0
    for method in methods_to_delete:
        removed, count = remove_method_from_file(target_file, method)
        if removed:
            print(f"  ✅ {method} 削除成功 ({count}個重複)")
            total_removed += 1
        else:
            print(f"  ⚠️ {method} 見つからず")
    
    print(f"  📊 Phase 1完了: {total_removed}/{len(methods_to_delete)} メソッド削除")
    return total_removed

if __name__ == "__main__":
    print("🚀 重複メソッド段階的削除開始")
    print("=" * 50)
    
    total = execute_phase_1()
    
    print("=" * 50)  
    print(f"🎯 削除完了: {total} メソッド")
