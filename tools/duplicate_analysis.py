#!/usr/bin/env python3
"""
重複・不要コード検出スクリプト
v2.0 - 2025年8月24日更新
"""
import os
import ast
import sys
from collections import defaultdict
from pathlib import Path

def get_project_root():
    """プロジェクトルートディレクトリを取得"""
    current = Path(__file__).parent
    while current.parent != current:
        if (current / 'src').exists() and (current / 'config').exists():
            return current
        current = current.parent
    return Path.cwd()

def analyze_method_duplicates():
    """メソッド重複検出"""
    project_root = get_project_root()
    
    # 主要ファイルのパス
    files_to_check = [
        project_root / 'src' / 'classes' / 'ui_ai_test.py',
        project_root / 'src' / 'classes' / 'ui_controller_ai.py',
        project_root / 'src' / 'classes' / 'ui_controller.py',
        project_root / 'src' / 'classes' / 'ui_controller_forms.py'
    ]
    
    method_signatures = defaultdict(list)
    
    for file_path in files_to_check:
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # メソッドの詳細情報を収集
                        method_info = {
                            'file': str(file_path),
                            'line': node.lineno,
                            'name': node.name,
                            'args': [arg.arg for arg in node.args.args],
                            'docstring': ast.get_docstring(node) or ""
                        }
                        method_signatures[node.name].append(method_info)
                        
            except Exception as e:
                print(f"⚠️ {file_path} メソッド解析エラー: {e}")
    
    return method_signatures

def analyze_imports():
    """インポート重複分析"""
    project_root = get_project_root()
    
    python_files = []
    src_dir = project_root / 'src'
    if src_dir.exists():
        for file_path in src_dir.rglob('*.py'):
            python_files.append(file_path)
    
    import_analysis = defaultdict(list)
    
    for file_path in python_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        import_analysis[alias.name].append(str(file_path))
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        import_name = f"{module}.{alias.name}"
                        import_analysis[import_name].append(str(file_path))
        except Exception as e:
            print(f"⚠️ {file_path} インポート解析エラー: {e}")
    
    return import_analysis

def detect_backup_files():
    """バックアップファイル検出"""
    project_root = get_project_root()
    
    backup_patterns = [
        'BACKUP_*.py',
        'temp_*.py', 
        '*_backup.py',
        '*_old.py',
        'test_phase_*.py'  # 一時的なテストファイル
    ]
    
    backup_files = []
    for pattern in backup_patterns:
        backup_files.extend(project_root.glob(pattern))
    
    return backup_files

def analyze_file_sizes():
    """ファイルサイズ分析"""
    project_root = get_project_root()
    
    key_files = [
        'src/classes/ui_ai_test.py',
        'src/classes/ui_controller_ai.py', 
        'src/classes/ui_controller.py',
        'src/classes/ui_controller_forms.py'
    ]
    
    file_stats = {}
    for file_rel_path in key_files:
        file_path = project_root / file_rel_path
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                file_stats[file_rel_path] = {
                    'lines': len(lines),
                    'size_kb': file_path.stat().st_size / 1024,
                    'methods': len([line for line in lines if line.strip().startswith('def ')])
                }
    
    return file_stats

def main():
    """メイン実行関数"""
    print("🔍 ARIM RDE Tool - 重複・不要コード分析")
    print("=" * 60)
    
    # 1. ファイルサイズ分析
    print("\n📊 主要ファイルサイズ分析:")
    file_stats = analyze_file_sizes()
    for file_path, stats in file_stats.items():
        print(f"  📁 {file_path}")
        print(f"     行数: {stats['lines']:,} 行")
        print(f"     サイズ: {stats['size_kb']:.1f} KB")
        print(f"     メソッド数: {stats['methods']} 個")
    
    # 2. メソッド重複分析  
    print("\n🔄 メソッド重複分析:")
    methods = analyze_method_duplicates()
    duplicate_methods = {k: v for k, v in methods.items() if len(v) > 1}
    
    if duplicate_methods:
        print(f"  ⚠️ 重複メソッド発見: {len(duplicate_methods)} 個")
        for method_name, occurrences in duplicate_methods.items():
            print(f"\n  🔸 {method_name}:")
            for occur in occurrences:
                print(f"     - {occur['file']}:{occur['line']}")
                if occur['args']:
                    print(f"       引数: {occur['args']}")
    else:
        print("  ✅ 重複メソッドなし")
    
    # 3. インポート重複分析
    print("\n📦 インポート重複分析:")
    imports = analyze_imports()
    duplicate_imports = {k: v for k, v in imports.items() if len(v) > 3}  # 3ファイル以上で使用
    
    if duplicate_imports:
        print(f"  📋 高頻度インポート: {len(duplicate_imports)} 個")
        for imp, files in list(duplicate_imports.items())[:5]:  # 上位5個のみ表示
            print(f"    {imp}: {len(files)} ファイル")
    else:
        print("  ✅ インポート最適化済み")
    
    # 4. バックアップファイル検出
    print("\n🗂️ バックアップファイル検出:")
    backup_files = detect_backup_files()
    
    if backup_files:
        print(f"  📦 バックアップファイル: {len(backup_files)} 個")
        for backup_file in backup_files:
            print(f"    - {backup_file.name}")
    else:
        print("  ✅ バックアップファイルなし")
    
    # 5. 総合評価
    print("\n🎯 総合評価:")
    total_duplicates = len(duplicate_methods)
    total_backups = len(backup_files)
    
    if total_duplicates == 0 and total_backups == 0:
        print("  ✅ クリーニング完了状態")
    else:
        print(f"  ⚠️ クリーニング必要: 重複{total_duplicates}個, バックアップ{total_backups}個")
        
        # 優先順位付きアクション提案
        print("\n📋 推奨アクション:")
        if total_duplicates > 0:
            print("  1. メソッド重複解消 (高優先度)")
        if total_backups > 0:
            print("  2. バックアップファイル整理 (中優先度)")
    
    print("\n" + "=" * 60)
    print("分析完了")

if __name__ == "__main__":
    main()
