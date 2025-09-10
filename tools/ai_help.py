#!/usr/bin/env python3
"""
AI性能テストツール - クイックスタートガイド

使用方法を表示し、基本的なテストを実行するヘルプスクリプトです。
"""

import os
import sys

def print_help():
    """使用方法を表示"""
    print("""
🤖 AI性能テストツール - クイックスタートガイド

📋 基本的な使用方法:

1. 単一テスト実行
   python tools/ai_test_cli.py --model gpt-4 --chars 500
   python tools/ai_test_cli.py --provider gemini --model gemini-1.5-flash --chars 1000 --padding
   python tools/ai_test_cli.py --provider local_llm --model llama3.2:3b --chars 2000 --repeat 3

2. 一括テスト実行
   tools/run_ai_tests.bat        # Windows バッチ
   tools/run_ai_tests.ps1        # PowerShell

3. 結果分析
   python tools/ai_result_analyzer.py output/log/ai_test_results_*.json

📋 パラメータ説明:

--provider     AIプロバイダー (openai, gemini, local_llm)
--model        使用するモデル名
--chars        テストプロンプトの文字数
--padding      文字数かさ増し機能を有効化
--repeat       テスト繰り返し回数
--output       結果保存ファイル名

📋 設定ファイル:

input/ai_config.json でAPI設定を管理してください。
サンプルファイル: input/ai_config.json.sample

📋 出力先:

テスト結果: output/log/ai_test_results_*.json
分析レポート: output/log/ai_performance_report_*.md
可視化グラフ: output/log/*.png

🔧 設定確認:

AI設定ファイルの状態を確認します...
""")
    
    # 設定ファイルの存在確認
    config_path = "input/ai_config.json"
    sample_path = "input/ai_config.json.sample"
    
    if os.path.exists(config_path):
        print(f"✅ AI設定ファイルが見つかりました: {config_path}")
        try:
            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            print("📊 設定されたプロバイダー:")
            for provider, settings in config.get("ai_providers", {}).items():
                enabled = "✅" if settings.get("enabled", False) else "❌"
                api_key = "設定済み" if settings.get("api_key") else "未設定"
                print(f"   {enabled} {provider}: API Key {api_key}")
                
        except Exception as e:
            print(f"⚠️ 設定ファイルの読み込みエラー: {e}")
    else:
        print(f"❌ AI設定ファイルが見つかりません: {config_path}")
        if os.path.exists(sample_path):
            print(f"📋 サンプルファイルをコピーして設定してください:")
            print(f"   copy {sample_path} {config_path}")
        else:
            print(f"⚠️ サンプルファイルも見つかりません: {sample_path}")
    
    print("""
🚀 クイックテスト実行例:

以下のコマンドで簡単なテストを実行できます:
""")

def run_quick_test():
    """クイックテストを実行"""
    print("🚀 クイックテストを開始します...")
    print("📝 OpenAI GPT-3.5-turbo で100文字のテストを実行")
    
    import subprocess
    try:
        result = subprocess.run([
            sys.executable, "tools/ai_test_cli.py",
            "--provider", "openai",
            "--model", "gpt-3.5-turbo", 
            "--chars", "100",
            "--output", "quick_test_result.json"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ クイックテスト成功!")
            print(result.stdout)
        else:
            print("❌ クイックテスト失敗:")
            print(result.stderr)
            
    except Exception as e:
        print(f"❌ テスト実行エラー: {e}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI性能テストツール - クイックスタートガイド")
    parser.add_argument("--quick-test", action="store_true", help="クイックテストを実行")
    
    args = parser.parse_args()
    
    print_help()
    
    if args.quick_test:
        print("\n" + "="*60)
        run_quick_test()
    else:
        print("\n💡 クイックテストを実行するには --quick-test オプションを使用してください")
        print("   python tools/ai_help.py --quick-test")

if __name__ == "__main__":
    main()
