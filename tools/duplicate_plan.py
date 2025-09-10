#!/usr/bin/env python3
"""
重複メソッド安全削除計画スクリプト
v2.0 - 2025年8月24日
"""
import os
import ast
from pathlib import Path
from collections import defaultdict

def analyze_method_usage():
    """メソッド使用状況の詳細分析"""
    project_root = Path.cwd()
    
    # 主要ファイルの重複分析
    primary_files = {
        'ui_ai_test': project_root / 'src' / 'classes' / 'ui_ai_test.py',
        'ui_controller_ai': project_root / 'src' / 'classes' / 'ui_controller_ai.py', 
        'ui_controller': project_root / 'src' / 'classes' / 'ui_controller.py',
        'ui_controller_forms': project_root / 'src' / 'classes' / 'ui_controller_forms.py'
    }
    
    # 重複メソッドの詳細情報
    duplicate_methods = {
        # 完全重複（即座削除可能）
        'immediate_deletion': [
            'test_ai_connection',      # ui_ai_test → ui_controller_ai に統合
            'send_ai_prompt',          # ui_ai_test → ui_controller_ai に統合
            '_validate_task_and_experiment_selection',  # ui_ai_test → ui_controller_ai に統合
            '_execute_analysis_single', # ui_ai_test → ui_controller_ai に統合
            '_execute_analysis_batch',  # ui_ai_test → ui_controller_ai に統合
        ],
        
        # 機能分散（慎重統合必要）
        'careful_integration': [
            '_load_arim_extension_data',  # 3ファイルに分散
            '_build_analysis_prompt',     # 3ファイルに分散
            '_merge_with_arim_data',      # 3ファイルに分散
            'show_text_area_expanded',    # 3ファイルに分散
        ],
        
        # UI重複（forms分離対象）
        'forms_separation': [
            'set_sample_inputs_enabled',  # controller → forms統合済み
            'update_sample_form',         # controller → forms統合済み  
            'validate_sample_info_early', # controller → forms統合済み
        ],
        
        # ライフサイクル重複（各クラス固有）
        'lifecycle_methods': [
            '__init__',                   # 各クラス固有のため保持
        ]
    }
    
    return duplicate_methods, primary_files

def create_deletion_plan():
    """段階的削除計画の作成"""
    duplicate_methods, primary_files = analyze_method_usage()
    
    deletion_plan = {
        'phase_1': {
            'description': 'AI機能完全重複削除（最優先）',
            'target_file': 'ui_ai_test.py',
            'methods_to_delete': [
                'test_ai_connection',
                'send_ai_prompt', 
                '_validate_task_and_experiment_selection',
                '_execute_analysis_single',
                '_execute_analysis_batch'
            ],
            'estimated_lines_saved': 200,
            'risk_level': 'LOW'
        },
        
        'phase_2': {
            'description': 'データ処理重複統合（中優先）',
            'target_files': ['ui_ai_test.py', 'ui_controller.py'],
            'methods_to_integrate': [
                '_load_arim_extension_data',
                '_merge_with_arim_data',
                '_load_experiment_data_for_task',
                '_load_experiment_data_for_task_list'
            ],
            'estimated_lines_saved': 150,
            'risk_level': 'MEDIUM'
        },
        
        'phase_3': {
            'description': 'UI関連重複削除（低優先）',
            'target_file': 'ui_controller.py',
            'methods_to_clean': [
                'show_progress',
                'update_progress',
                'hide_progress',
                '_format_elapsed_time'
            ],
            'estimated_lines_saved': 100,
            'risk_level': 'LOW'
        }
    }
    
    return deletion_plan

def generate_deletion_script():
    """削除スクリプトの生成"""
    deletion_plan = create_deletion_plan()
    
    script_content = '''#!/usr/bin/env python3
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
    pattern = rf'\\n\\s*def {method_name}\\(.*?\\):(.*?)(?=\\n\\s*def |\\n\\s*class |\\Z)'
    
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
'''
    
    return script_content

def main():
    """メイン実行関数"""
    print("📋 重複メソッド削除計画生成")
    print("=" * 50)
    
    # 削除計画分析
    deletion_plan = create_deletion_plan()
    
    print("🎯 削除計画概要:")
    total_estimated_savings = 0
    
    for phase, details in deletion_plan.items():
        print(f"\n📌 {phase.upper()}:")
        print(f"   説明: {details['description']}")
        print(f"   対象: {details.get('target_file', details.get('target_files', 'N/A'))}")
        print(f"   予想削除行数: {details['estimated_lines_saved']} 行")
        print(f"   リスク: {details['risk_level']}")
        total_estimated_savings += details['estimated_lines_saved']
    
    print(f"\n🎊 総予想削減効果: {total_estimated_savings} 行")
    
    # 削除スクリプト生成
    script_content = generate_deletion_script()
    script_path = Path('tools/duplicate_remover.py')
    
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print(f"\n📝 削除スクリプト生成: {script_path}")
    print("=" * 50)
    print("計画生成完了")

if __name__ == "__main__":
    main()
