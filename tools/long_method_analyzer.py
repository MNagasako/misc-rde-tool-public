#!/usr/bin/env python3
"""
長いメソッド分析ツール - Phase 2 長いメソッド分割用
ARIM RDE Tool リファクタリング支援
"""
import ast
import os
from pathlib import Path
from typing import List, Dict, Tuple
import re

def get_project_root():
    """プロジェクトルートディレクトリを取得"""
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if (parent / 'src').exists():
            return parent
    return current_path.parent

def analyze_method_length(file_path: Path) -> List[Dict]:
    """ファイル内のメソッド長を分析"""
    if not file_path.exists():
        return []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
    except Exception as e:
        print(f"ファイル読み込みエラー {file_path}: {e}")
        return []

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        print(f"構文エラー {file_path}: {e}")
        return []

    methods = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start_line = node.lineno
            end_line = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else start_line
            
            # より正確な終了行を計算
            if end_line == start_line:
                # docstringと関数本体を考慮した終了行推定
                method_lines = []
                in_method = False
                indent_level = None
                
                for i, line in enumerate(lines[start_line-1:], start_line):
                    if i == start_line:
                        in_method = True
                        # インデントレベルを記録
                        stripped = line.lstrip()
                        indent_level = len(line) - len(stripped)
                        method_lines.append(line)
                        continue
                    
                    if in_method:
                        stripped = line.strip()
                        if stripped == "":
                            method_lines.append(line)
                            continue
                        
                        # インデントレベルをチェック
                        current_indent = len(line) - len(line.lstrip())
                        
                        # メソッドの終了条件：同じかより少ないインデント、かつ関数・クラス定義
                        if (current_indent <= indent_level and 
                            (stripped.startswith('def ') or stripped.startswith('class ') or 
                             stripped.startswith('async def '))):
                            break
                        
                        method_lines.append(line)
                        end_line = i
                
                if not method_lines:
                    end_line = start_line
            
            method_length = end_line - start_line + 1
            
            # 実際のコード行数を計算（空行・コメント除く）
            actual_code_lines = 0
            for i in range(start_line-1, min(end_line, len(lines))):
                line = lines[i].strip()
                if line and not line.startswith('#'):
                    actual_code_lines += 1
            
            methods.append({
                'name': node.name,
                'start_line': start_line,
                'end_line': end_line,
                'total_lines': method_length,
                'code_lines': actual_code_lines,
                'class_name': get_class_name(node, tree)
            })
    
    return sorted(methods, key=lambda x: x['total_lines'], reverse=True)

def get_class_name(method_node, tree):
    """メソッドが属するクラス名を取得"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in ast.walk(node):
                if child is method_node:
                    return node.name
    return "モジュールレベル"

def analyze_target_files() -> Dict[str, List[Dict]]:
    """対象ファイル群の長いメソッド分析"""
    project_root = get_project_root()
    
    target_files = [
        'src/classes/ui_controller.py',
        'src/classes/ui_controller_ai.py', 
        'src/classes/ui_controller_core.py',
        'src/classes/ai_data_manager.py',
        'src/classes/ui_dialogs.py',
        'src/classes/ui_ai_test.py',
        'src/classes/ui_controller_forms.py',
        'src/classes/ui_controller_data.py'
    ]
    
    results = {}
    
    for file_rel_path in target_files:
        file_path = project_root / file_rel_path
        if file_path.exists():
            methods = analyze_method_length(file_path)
            # 100行以上のメソッドのみ抽出
            long_methods = [m for m in methods if m['total_lines'] >= 100]
            if long_methods:
                results[file_rel_path] = long_methods
        else:
            print(f"ファイルが見つかりません: {file_path}")
    
    return results

def generate_refactor_plan(analysis_results: Dict[str, List[Dict]]) -> str:
    """リファクタリング計画を生成"""
    plan = """# Phase 2 長いメソッド分割計画 v2.0
## 🎯 分析結果に基づく優先順位

### **緊急対応必要 (500行以上)**
"""
    
    urgent_methods = []
    high_methods = []
    medium_methods = []
    
    for file_path, methods in analysis_results.items():
        for method in methods:
            method['file'] = file_path
            if method['total_lines'] >= 500:
                urgent_methods.append(method)
            elif method['total_lines'] >= 200:
                high_methods.append(method)
            else:
                medium_methods.append(method)
    
    # 優先順位別にソート
    urgent_methods.sort(key=lambda x: x['total_lines'], reverse=True)
    high_methods.sort(key=lambda x: x['total_lines'], reverse=True)
    medium_methods.sort(key=lambda x: x['total_lines'], reverse=True)
    
    if urgent_methods:
        for i, method in enumerate(urgent_methods, 1):
            plan += f"{i}. **{method['file']}::{method['class_name']}.{method['name']}**\n"
            plan += f"   - 総行数: {method['total_lines']}行 (L{method['start_line']}-{method['end_line']})\n"
            plan += f"   - コード行数: {method['code_lines']}行\n"
            plan += f"   - 緊急度: 🔴 最高\n\n"
    
    plan += "\n### **高優先対応 (200-499行)**\n"
    if high_methods:
        for i, method in enumerate(high_methods, 1):
            plan += f"{i}. **{method['file']}::{method['class_name']}.{method['name']}**\n"
            plan += f"   - 総行数: {method['total_lines']}行 (L{method['start_line']}-{method['end_line']})\n"
            plan += f"   - コード行数: {method['code_lines']}行\n"
            plan += f"   - 優先度: 🟡 高\n\n"
    
    plan += "\n### **中優先対応 (100-199行)**\n"
    if medium_methods:
        for i, method in enumerate(medium_methods, 1):
            plan += f"{i}. **{method['file']}::{method['class_name']}.{method['name']}**\n"
            plan += f"   - 総行数: {method['total_lines']}行 (L{method['start_line']}-{method['end_line']})\n"
            plan += f"   - コード行数: {method['code_lines']}行\n"
            plan += f"   - 優先度: 🟢 中\n\n"
    
    plan += f"""
## 📊 分析サマリー
- **緊急対応**: {len(urgent_methods)}メソッド
- **高優先対応**: {len(high_methods)}メソッド  
- **中優先対応**: {len(medium_methods)}メソッド
- **総対象**: {len(urgent_methods) + len(high_methods) + len(medium_methods)}メソッド

## 🛡️ 実行方針
1. **緊急対応から順次実行**
2. **1メソッドずつ段階的分割**
3. **各段階でgitコミット必須**
4. **通常起動での動作確認必須**
5. **委譲パターンで安全な移行**
"""
    
    return plan

def main():
    """メイン実行"""
    print("🔍 Phase 2 長いメソッド分析開始")
    print("=" * 50)
    
    # 分析実行
    results = analyze_target_files()
    
    # 結果表示
    total_long_methods = 0
    for file_path, methods in results.items():
        print(f"\n📁 {file_path}")
        for method in methods:
            print(f"  🔴 {method['class_name']}.{method['name']}: {method['total_lines']}行 "
                  f"(L{method['start_line']}-{method['end_line']})")
            total_long_methods += 1
    
    print(f"\n📊 長いメソッド総数: {total_long_methods}個")
    
    # 計画ファイル生成
    plan_content = generate_refactor_plan(results)
    
    plan_file = get_project_root() / "PHASE2_LONG_METHOD_ANALYSIS_v2.md"
    with open(plan_file, 'w', encoding='utf-8') as f:
        f.write(plan_content)
    
    print(f"\n✅ 分析完了: {plan_file}")
    
    return results

if __name__ == "__main__":
    main()
