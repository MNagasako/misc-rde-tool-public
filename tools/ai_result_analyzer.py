#!/usr/bin/env python3
"""
AI性能テスト結果分析ツール - ARIM RDE Tool v1.13.1

概要:
ai_test_cli.pyで生成されたテスト結果を分析し、
パフォーマンス比較レポートを生成します。

使用例:
python tools/ai_result_analyzer.py output/log/ai_test_results_*.json
python tools/ai_result_analyzer.py --directory output/log --pattern "ai_test_*_20250818_*.json"
"""

import os
import sys
import json
import glob
import argparse
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
from typing import List, Dict, Any
import seaborn as sns

# パス管理システムを使用（CWD非依存）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config.common import get_dynamic_file_path

# 日本語フォント設定
plt.rcParams['font.family'] = ['DejaVu Sans', 'Arial Unicode MS', 'Hiragino Sans']

class AIResultAnalyzer:
    """AI性能テスト結果分析クラス"""
    
    def __init__(self):
        self.results_data = []
        self.summary_stats = {}
        
    def load_results(self, file_patterns: List[str]) -> int:
        """結果ファイルを読み込み"""
        loaded_count = 0
        
        for pattern in file_patterns:
            # パターンマッチングでファイル検索
            files = glob.glob(pattern)
            
            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                    # データが配列形式の場合
                    if isinstance(data, list):
                        for item in data:
                            item['source_file'] = os.path.basename(file_path)
                            self.results_data.append(item)
                    # データが単一オブジェクトの場合
                    else:
                        data['source_file'] = os.path.basename(file_path)
                        self.results_data.append(data)
                    
                    loaded_count += 1
                    print(f"✅ 読み込み完了: {file_path}")
                    
                except Exception as e:
                    print(f"❌ 読み込みエラー: {file_path} - {e}")
        
        print(f"📊 総データ数: {len(self.results_data)} 件 ({loaded_count} ファイル)")
        return loaded_count
    
    def analyze_performance(self) -> Dict[str, Any]:
        """パフォーマンス分析を実行"""
        if not self.results_data:
            print("❌ 分析対象データがありません")
            return {}
        
        # 成功したテストのみ分析
        successful_tests = [r for r in self.results_data if r.get("success", False)]
        
        if not successful_tests:
            print("❌ 成功したテストがありません")
            return {}
        
        # DataFrameに変換
        df = pd.DataFrame(successful_tests)
        
        # 基本統計の計算
        analysis = {
            "total_tests": len(self.results_data),
            "successful_tests": len(successful_tests),
            "success_rate": len(successful_tests) / len(self.results_data) * 100,
            "models": df['model'].unique().tolist(),
            "response_time_stats": {
                "mean": df['response_time'].mean(),
                "median": df['response_time'].median(),
                "std": df['response_time'].std(),
                "min": df['response_time'].min(),
                "max": df['response_time'].max()
            }
        }
        
        # モデル別統計
        model_stats = {}
        for model in analysis["models"]:
            model_data = df[df['model'] == model]
            model_stats[model] = {
                "count": len(model_data),
                "avg_response_time": model_data['response_time'].mean(),
                "avg_tokens": model_data['tokens_used'].mean() if 'tokens_used' in model_data.columns else 0,
                "success_rate": len(model_data) / len([r for r in self.results_data if r.get('model') == model]) * 100
            }
        
        analysis["model_stats"] = model_stats
        
        # プロンプト長別統計
        if 'prompt_length' in df.columns:
            prompt_stats = {}
            for length in df['prompt_length'].unique():
                length_data = df[df['prompt_length'] == length]
                prompt_stats[int(length)] = {
                    "count": len(length_data),
                    "avg_response_time": length_data['response_time'].mean(),
                    "models_tested": length_data['model'].unique().tolist()
                }
            analysis["prompt_length_stats"] = prompt_stats
        
        self.summary_stats = analysis
        return analysis
    
    def generate_visualizations(self, output_dir: str = "output/log"):
        """可視化レポートを生成"""
        if not self.results_data:
            print("❌ 可視化対象データがありません")
            return
        
        # 出力ディレクトリ作成
        os.makedirs(output_dir, exist_ok=True)
        
        # 成功したテストのみ使用
        successful_tests = [r for r in self.results_data if r.get("success", False)]
        df = pd.DataFrame(successful_tests)
        
        if df.empty:
            print("❌ 可視化対象の成功データがありません")
            return
        
        # スタイル設定
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")
        
        # 1. レスポンス時間の分布
        plt.figure(figsize=(12, 6))
        plt.subplot(1, 2, 1)
        plt.hist(df['response_time'], bins=20, alpha=0.7, edgecolor='black')
        plt.title('Response Time Distribution')
        plt.xlabel('Response Time (seconds)')
        plt.ylabel('Frequency')
        plt.grid(True, alpha=0.3)
        
        # 2. モデル別レスポンス時間比較
        plt.subplot(1, 2, 2)
        if 'model' in df.columns:
            sns.boxplot(data=df, x='model', y='response_time')
            plt.title('Response Time by Model')
            plt.xlabel('Model')
            plt.ylabel('Response Time (seconds)')
            plt.xticks(rotation=45)
        
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'ai_performance_overview.png'), dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. プロンプト長とレスポンス時間の関係
        if 'prompt_length' in df.columns:
            plt.figure(figsize=(10, 6))
            for model in df['model'].unique():
                model_data = df[df['model'] == model]
                plt.scatter(model_data['prompt_length'], model_data['response_time'], 
                          label=model, alpha=0.7, s=50)
            
            plt.xlabel('Prompt Length (characters)')
            plt.ylabel('Response Time (seconds)')
            plt.title('Response Time vs Prompt Length by Model')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.savefig(os.path.join(output_dir, 'prompt_length_vs_response_time.png'), dpi=300, bbox_inches='tight')
            plt.close()
        
        # 4. 成功率の比較
        success_rates = {}
        for model in df['model'].unique():
            total_tests = len([r for r in self.results_data if r.get('model') == model])
            successful_tests = len(df[df['model'] == model])
            success_rates[model] = successful_tests / total_tests * 100
        
        plt.figure(figsize=(10, 6))
        models = list(success_rates.keys())
        rates = list(success_rates.values())
        
        bars = plt.bar(models, rates, alpha=0.8, edgecolor='black')
        plt.title('Success Rate by Model')
        plt.xlabel('Model')
        plt.ylabel('Success Rate (%)')
        plt.ylim(0, 105)
        
        # 成功率の値をバーの上に表示
        for bar, rate in zip(bars, rates):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1, 
                    f'{rate:.1f}%', ha='center', va='bottom')
        
        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3, axis='y')
        plt.savefig(os.path.join(output_dir, 'success_rate_by_model.png'), dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"📈 可視化レポートを生成しました: {output_dir}")
    
    def generate_report(self, output_file: str = None) -> str:
        """詳細レポートを生成"""
        if not self.summary_stats:
            print("❌ 分析データがありません。先にanalyze_performance()を実行してください。")
            return ""
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        report = f"""
# AI性能テスト分析レポート

**生成日時**: {timestamp}  
**分析対象**: {self.summary_stats['total_tests']} 件のテスト結果

## 📊 全体サマリ

- **総テスト数**: {self.summary_stats['total_tests']}
- **成功テスト数**: {self.summary_stats['successful_tests']}
- **成功率**: {self.summary_stats['success_rate']:.1f}%
- **テスト対象モデル**: {', '.join(self.summary_stats['models'])}

## ⏱️ レスポンス時間統計

- **平均**: {self.summary_stats['response_time_stats']['mean']:.2f}秒
- **中央値**: {self.summary_stats['response_time_stats']['median']:.2f}秒
- **標準偏差**: {self.summary_stats['response_time_stats']['std']:.2f}秒
- **最短**: {self.summary_stats['response_time_stats']['min']:.2f}秒
- **最長**: {self.summary_stats['response_time_stats']['max']:.2f}秒

## 🤖 モデル別パフォーマンス

"""
        
        for model, stats in self.summary_stats['model_stats'].items():
            report += f"""
### {model}
- **テスト数**: {stats['count']}回
- **成功率**: {stats['success_rate']:.1f}%
- **平均レスポンス時間**: {stats['avg_response_time']:.2f}秒
- **平均トークン使用量**: {stats['avg_tokens']:.0f}
"""
        
        if 'prompt_length_stats' in self.summary_stats:
            report += "\n## 📏 プロンプト長別統計\n"
            
            for length, stats in sorted(self.summary_stats['prompt_length_stats'].items()):
                report += f"""
### {length}文字
- **テスト数**: {stats['count']}回
- **平均レスポンス時間**: {stats['avg_response_time']:.2f}秒
- **テスト対象モデル**: {', '.join(stats['models_tested'])}
"""
        
        report += f"""

## 📈 可視化レポート

以下のグラフが生成されました:
- `ai_performance_overview.png`: レスポンス時間分布とモデル別比較
- `prompt_length_vs_response_time.png`: プロンプト長とレスポンス時間の関係
- `success_rate_by_model.png`: モデル別成功率

## 🔍 推奨事項

"""
        
        # 推奨事項の自動生成
        best_model = min(self.summary_stats['model_stats'].items(), 
                        key=lambda x: x[1]['avg_response_time'])
        fastest_model = best_model[0]
        fastest_time = best_model[1]['avg_response_time']
        
        report += f"- **最高速モデル**: {fastest_model} (平均{fastest_time:.2f}秒)\n"
        
        if self.summary_stats['success_rate'] < 95:
            report += "- **成功率改善**: 全体的な成功率が95%を下回っています。APIキーとネットワーク接続を確認してください。\n"
        
        if self.summary_stats['response_time_stats']['max'] > 30:
            report += "- **タイムアウト設定**: 最大レスポンス時間が30秒を超えています。タイムアウト設定の見直しを検討してください。\n"
        
        report += "\n---\n*このレポートはai_result_analyzer.pyによって自動生成されました。*\n"
        
        # ファイル保存
        if not output_file:
            timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"ai_performance_report_{timestamp_file}.md"
        
        output_path = get_dynamic_file_path(f"output/log/{output_file}")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"📄 分析レポートを生成しました: {output_path}")
        return report

def main():
    parser = argparse.ArgumentParser(description="AI性能テスト結果分析ツール")
    parser.add_argument("files", nargs="*", help="分析対象のJSONファイル")
    parser.add_argument("--directory", "-d", type=str, help="結果ファイルのディレクトリ")
    parser.add_argument("--pattern", "-p", type=str, default="ai_test_*.json", 
                       help="ファイル名パターン (default: ai_test_*.json)")
    parser.add_argument("--output", "-o", type=str, help="レポート出力ファイル名")
    parser.add_argument("--no-viz", action="store_true", help="可視化を無効化")
    
    args = parser.parse_args()
    
    # 分析対象ファイルの決定
    file_patterns = []
    
    if args.files:
        file_patterns = args.files
    elif args.directory:
        pattern_path = os.path.join(args.directory, args.pattern)
        file_patterns = [pattern_path]
    else:
        # デフォルト: output/logディレクトリのai_test_*.json
        default_pattern = os.path.join("output", "log", args.pattern)
        file_patterns = [default_pattern]
    
    # 分析実行
    analyzer = AIResultAnalyzer()
    
    print("🔍 結果ファイルを読み込み中...")
    loaded_count = analyzer.load_results(file_patterns)
    
    if loaded_count == 0:
        print("❌ 読み込めるファイルがありませんでした。")
        return 1
    
    print("📊 パフォーマンス分析を実行中...")
    analysis = analyzer.analyze_performance()
    
    if not analysis:
        print("❌ 分析に失敗しました。")
        return 1
    
    # 可視化
    if not args.no_viz:
        print("📈 可視化レポートを生成中...")
        analyzer.generate_visualizations()
    
    # レポート生成
    print("📄 分析レポートを生成中...")
    analyzer.generate_report(args.output)
    
    print("✅ 分析完了!")
    return 0

if __name__ == "__main__":
    exit(main())
